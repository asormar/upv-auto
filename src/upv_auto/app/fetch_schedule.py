"""Use case: log in and read the configured activity's weekly group table.

Returns the parsed groups so callers can print them (`list_groups`) or serve
them (the web adapter). Failures are logged and notified here, and reported to
the caller as `None`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from upv_auto.app.authenticate import authenticate
from upv_auto.config import AppConfig
from upv_auto.domain.models import BookingOutcome, GroupAvailability
from upv_auto.ports import ActivityTableClient, Authenticator, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)


def fetch_schedule(
    config: AppConfig,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
    table_client: ActivityTableClient,
    *,
    on_login_failure: Callable[[str], None] | None = None,
) -> dict[str, GroupAvailability] | None:
    """Log in and fetch the activity table, or return None if that failed.

    `on_login_failure` is passed straight to `authenticate`, so a caller can
    distinguish credentials the UPV rejected from the UPV being down.
    """
    session = authenticate(
        config.credentials, authenticator, verifier, notifier, clock, on_failure=on_login_failure
    )
    if session is None:
        return None

    snapshot = table_client.fetch_groups(session)

    if snapshot.failure is BookingOutcome.SESSION_EXPIRED:
        logger.error("Session expired while fetching the activity table")
        notifier.notify("Session expired while fetching the activity table.")
        return None

    if snapshot.failure is BookingOutcome.ERROR:
        logger.error("Failed to fetch activity table: %s", snapshot.message)
        notifier.notify(f"Failed to fetch activity table: {snapshot.message}")
        return None

    return snapshot.groups
