"""Use case: refresh one user's cached schedule (schedule-refresh spec).

Runs once per claimed `refresh_requests` row: unseal that user's own
credentials, log in, fetch the UPV activity table, cache the result, and
mark the request `done` or `failed`. Reused by the `refresh` CLI command,
invoked by `refresh.yml` with only the opaque `request_id` GitHub Actions
input that `supabase/functions/refresh/index.ts` dispatches (design.md's
"Refresh dispatch" decision) — this use case never receives a user id or
email as an argument; it learns both from
`directory.claim_request(request_id)`.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Callable

from upv_auto.app.fetch_schedule import fetch_schedule
from upv_auto.config import AppConfig
from upv_auto.domain.errors import CredentialsUnavailable
from upv_auto.domain.models import Credentials
from upv_auto.ports import (
    ActivityTableClient,
    Authenticator,
    Clock,
    CredentialOpener,
    Notifier,
    SessionVerifier,
    UserDirectory,
)

logger = logging.getLogger(__name__)

OnCredentialsOpened = Callable[[Credentials], None]


def refresh_user(
    request_id: str,
    config: AppConfig,
    directory: UserDirectory,
    credential_opener: CredentialOpener,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
    table_client: ActivityTableClient,
    *,
    on_credentials_opened: OnCredentialsOpened | None = None,
) -> int:
    """Fetch and cache one user's schedule for an already-claimed refresh request.

    Returns 0 on success, 1 otherwise. Never raises: every outcome —
    including one this function did not anticipate — ends by calling
    `directory.finish_request(...)`, so the frontend's Realtime hook
    (`useRefreshStatus.ts`) never sees a request stuck `pending` forever.

    `on_credentials_opened` mirrors `app.run_batch`'s hook of the same name:
    called the moment credentials are unsealed, before any login attempt, so
    the CLI can register the plaintext with `RedactingFilter` and emit
    GitHub Actions `::add-mask::` lines without this use case importing any
    adapter.
    """
    try:
        job = directory.claim_request(request_id)
    except CredentialsUnavailable:
        # Signed up, no UPV credentials saved yet (the sign-in refresh can
        # reach this before the credentials form is submitted). Close the
        # request so the web stops showing a pending refresh.
        logger.warning("No stored credentials for this refresh request")
        directory.finish_request(request_id, ok=False, error_code="credentials_unavailable")
        return 1
    if job is None:
        logger.error("Refresh request not found or already finished")
        return 1

    try:
        credentials = credential_opener.open(job.sealed_credentials, job.key_id)
    except CredentialsUnavailable:
        logger.warning("Could not unseal credentials for this refresh request")
        directory.finish_request(request_id, ok=False, error_code="credentials_unavailable")
        return 1

    if on_credentials_opened is not None:
        on_credentials_opened(credentials)

    # No bookings, no email: a refresh only reads the activity table.
    user_config = dataclasses.replace(config, credentials=credentials, email=None)

    try:
        groups = fetch_schedule(user_config, authenticator, verifier, notifier, clock, table_client)
    except Exception as exc:  # one user's refresh must never crash the runner
        logger.error("Unexpected error while refreshing: %s", type(exc).__name__)
        directory.finish_request(request_id, ok=False, error_code="error")
        return 1

    if groups is None:
        directory.finish_request(request_id, ok=False, error_code="fetch_failed")
        return 1

    directory.save_schedule(job.user_id, groups)
    directory.finish_request(request_id, ok=True, error_code=None)
    logger.info("Refresh finished: schedule cached")
    return 0
