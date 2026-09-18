"""Use case: log in and print every configured activity's group states.

Meant for interactive use, to pick `group_code` values for `config.yaml`.
Prints directly to stdout; never sends a notification on success (login
failures are still reported through `notifier`, same as every other use
case).
"""

from __future__ import annotations

import logging

from upv_auto.app.fetch_schedule import fetch_schedule
from upv_auto.config import AppConfig
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
    groups = fetch_schedule(config, authenticator, verifier, notifier, clock, table_client)
    if groups is None:
        return False

    for code in sorted(groups):
        group = groups[code]
        free = "" if group.free_places is None else f", {group.free_places} free"
        when = f" [{group.day} {group.time}]" if group.day and group.time else ""
        print(f"{code}: {group.state.name}{free}{when}")

    return True
