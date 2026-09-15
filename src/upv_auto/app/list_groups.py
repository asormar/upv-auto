"""Use case: log in and print every configured activity's group states.

Meant for interactive use, to pick `group_code` values for `config.yaml`.
Prints directly to stdout; never sends a notification on success (login
failures are still reported through `notifier`, same as every other use
case).
"""

from __future__ import annotations

import logging

from upv_auto.app.authenticate import authenticate
from upv_auto.config import AppConfig
from upv_auto.domain.models import BookingOutcome
from upv_auto.ports import ActivityTableClient, Authenticator, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)


def list_groups(
    config: AppConfig,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
    table_client: ActivityTableClient,
) -> bool:
    """Log in, fetch the activity table, and print each group's state.

    Returns True iff login succeeded and the table was fetched and parsed.
    """
    session = authenticate(config.credentials, authenticator, verifier, notifier, clock)
    if session is None:
        return False

    snapshot = table_client.fetch_groups(session)

    if snapshot.failure is BookingOutcome.SESSION_EXPIRED:
        logger.error("Session expired while fetching the activity table")
        notifier.notify("Session expired while fetching the activity table.")
        return False

    if snapshot.failure is BookingOutcome.ERROR:
        logger.error("Failed to fetch activity table: %s", snapshot.message)
        notifier.notify(f"Failed to fetch activity table: {snapshot.message}")
        return False

    for code in sorted(snapshot.groups):
        group = snapshot.groups[code]
        free = "" if group.free_places is None else f", {group.free_places} free"
        print(f"{code}: {group.state.name}{free}")

    return True
