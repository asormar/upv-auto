"""Use case: log in and print every configured activity's group states.

Meant for interactive use, to pick `group_code` values for `config.yaml`.
Prints directly to stdout; never sends a notification on success (login
failures are still reported through `notifier`, same as every other use
case).
"""

from __future__ import annotations

import logging

import httpx

from upv_auto.adapters.httpx_session import build_client
from upv_auto.adapters.upv_activities_parser import parse_groups
from upv_auto.adapters.upv_urls import CAS_HOST, DEFAULT_BASE_URL, activity_table_url
from upv_auto.app.authenticate import authenticate
from upv_auto.config import AppConfig
from upv_auto.ports import Authenticator, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)

RESPONSE_ENCODING = "iso-8859-15"


def list_groups(
    config: AppConfig,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
    *,
    base_url: str = DEFAULT_BASE_URL,
    cas_host: str = CAS_HOST,
) -> bool:
    """Log in, fetch the activity table, and print each group's state.

    Returns True iff login succeeded and the table was fetched and parsed.
    """
    session = authenticate(config.credentials, authenticator, verifier, notifier, clock)
    if session is None:
        return False

    url = activity_table_url(config.activity, base_url=base_url)

    with build_client(session) as client:
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch activity table: %s", exc)
            notifier.notify(f"Failed to fetch activity table: {exc}")
            return False

    if httpx.URL(str(response.url)).host == cas_host:
        logger.error("Session expired while fetching the activity table")
        notifier.notify("Session expired while fetching the activity table.")
        return False

    if response.status_code >= 400:
        logger.error("Activity table request returned HTTP %d", response.status_code)
        notifier.notify(f"Activity table request returned HTTP {response.status_code}.")
        return False

    response.encoding = RESPONSE_ENCODING
    groups = parse_groups(response.text)

    for code in sorted(groups):
        group = groups[code]
        free = "" if group.free_places is None else f", {group.free_places} free"
        print(f"{code}: {group.state.name}{free}")

    return True
