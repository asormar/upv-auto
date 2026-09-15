"""Activity table HTTP adapter.

Flow, reverse-engineered from a real booking session (see project README /
task notes for the HAR analysis):

1. GET the weekly activity table for the configured activity
   (`fetch_groups`). Each cell parses to a `GroupAvailability` (state
   BOOKABLE/FULL/ENROLLED/UNAVAILABLE, free places, and for bookable groups
   the scraped booking link).
2. To attempt a booking, GET the group's scraped booking link
   (`follow_booking`; the opaque `p_codgrupo_mat` id changes between groups
   and over time, so it is always read from the table right before booking,
   never hardcoded). UPV redirects that request back to the (now refreshed)
   activity table, so the response is parsed exactly like `fetch_groups` and
   returned as another `TableSnapshot` — the caller reuses it instead of
   downloading the table again.

Any response whose final URL host is the CAS host means the session has
expired. Network errors, timeouts, 4xx and 5xx responses are mapped to
`BookingOutcome.ERROR` (never raised) so the retry loop in
`app/book_slot.py` can keep trying.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

from upv_auto.adapters.httpx_session import build_client
from upv_auto.adapters.upv_activities_parser import parse_groups
from upv_auto.adapters.upv_urls import CAS_HOST, DEFAULT_BASE_URL, activity_table_url
from upv_auto.domain.models import Activity, BookingOutcome, GroupAvailability, Session, TableSnapshot

logger = logging.getLogger(__name__)

RESPONSE_ENCODING = "iso-8859-15"


class HttpxActivityTableClient:
    """Reads and books UPV activity table groups over plain HTTP.

    Keeps one `httpx.Client` alive across calls while the same `Session`
    object keeps being used, so repeated reads in the same booking round
    reuse the TLS connection (and any cookies UPV refreshes along the way)
    instead of paying connection setup for every request. A different
    `Session` (e.g. after a re-login) rebuilds the client.
    """

    def __init__(
        self,
        activity: Activity,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        cas_host: str = CAS_HOST,
    ) -> None:
        self._activity = activity
        self._base_url = base_url
        self._transport = transport
        self._cas_host = cas_host
        self._client: httpx.Client | None = None
        self._session: Session | None = None

    def fetch_groups(self, session: Session) -> TableSnapshot:
        client = self._client_for(session)
        response, failure = self._get(client, activity_table_url(self._activity, base_url=self._base_url))
        if failure is not None:
            return failure
        return TableSnapshot(groups=parse_groups(response.text))

    def follow_booking(self, session: Session, group: GroupAvailability) -> TableSnapshot:
        if not group.booking_path:  # pragma: no cover - defensive, BOOKABLE always carries a path
            logger.error("Group %s is BOOKABLE but has no booking link", group.code)
            return TableSnapshot(failure=BookingOutcome.ERROR, message="bookable group has no booking link")

        client = self._client_for(session)
        booking_url = urljoin(self._base_url, group.booking_path)
        response, failure = self._get(client, booking_url)
        if failure is not None:
            return failure
        return TableSnapshot(groups=parse_groups(response.text))

    def _client_for(self, session: Session) -> httpx.Client:
        """Return the live client for `session`, rebuilding it if the session changed."""
        if self._client is None or self._session is not session:
            if self._client is not None:
                self._client.close()
            self._client = build_client(session, transport=self._transport)
            self._session = session
        return self._client

    def _get(self, client: httpx.Client, url: str) -> tuple[httpx.Response | None, TableSnapshot | None]:
        """GET `url`, classifying the outcome. Never raises."""
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("Request to UPV failed: %s", exc)
            return None, TableSnapshot(failure=BookingOutcome.ERROR, message=str(exc))

        if httpx.URL(str(response.url)).host == self._cas_host:
            logger.info("Session expired (redirected to CAS)")
            return None, TableSnapshot(failure=BookingOutcome.SESSION_EXPIRED)

        if response.status_code >= 400:
            logger.warning("UPV returned HTTP %d for %s", response.status_code, url)
            return None, TableSnapshot(failure=BookingOutcome.ERROR, message=f"HTTP {response.status_code}")

        response.encoding = RESPONSE_ENCODING
        return response, None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._session = None

    def __enter__(self) -> "HttpxActivityTableClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
