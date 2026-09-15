"""Booking HTTP adapter.

Flow, reverse-engineered from a real booking session (see project README /
task notes for the HAR analysis):

1. GET the weekly activity table for the configured activity.
2. Find the configured group's cell:
   - already ENROLLED -> ALREADY_ENROLLED. Not BOOKED: the page has no week
     indicator and may still show the previous week right after opening time.
   - FULL -> TAKEN.
   - UNAVAILABLE or missing from the table -> NOT_OPEN_YET (retry later).
   - BOOKABLE -> GET the scraped booking link (never hardcoded: the opaque
     `p_codgrupo_mat` id changes between groups and over time), then re-parse
     the resulting page and map the same group's new state to an outcome.

Any response whose final URL host is the CAS host means the session has
expired. Network errors, timeouts, and 5xx responses are mapped to ERROR
(never raised) so the retry loop in `app/book_slot.py` can keep trying.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

from upv_auto.adapters.httpx_session import build_client
from upv_auto.adapters.upv_activities_parser import parse_groups
from upv_auto.adapters.upv_urls import CAS_HOST, DEFAULT_BASE_URL, activity_table_url
from upv_auto.domain.models import Activity, BookingOutcome, BookingResult, GroupState, Session, Slot

logger = logging.getLogger(__name__)

RESPONSE_ENCODING = "iso-8859-15"


class HttpxBookingClient:
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

    def book(self, session: Session, slot: Slot) -> BookingResult:
        with build_client(session, transport=self._transport) as client:
            response, error = self._get(client, activity_table_url(self._activity, base_url=self._base_url))
            if error is not None:
                return error

            groups = parse_groups(response.text)
            group = groups.get(slot.group_code)

            if group is None:
                logger.info("Group %s not listed in the activity table", slot.group_code)
                return BookingResult(BookingOutcome.NOT_OPEN_YET, "group not listed")

            if group.state is GroupState.ENROLLED:
                # The page has no week indicator, so this may be last week's table.
                logger.info("Group %s already shows as enrolled", slot.group_code)
                return BookingResult(BookingOutcome.ALREADY_ENROLLED, "already enrolled")

            if group.state is GroupState.FULL:
                logger.info("Group %s is full", slot.group_code)
                return BookingResult(BookingOutcome.TAKEN, "group full")

            if group.state is GroupState.UNAVAILABLE:
                logger.info(
                    "Group %s not bookable yet (%s free)", slot.group_code, group.free_places
                )
                return BookingResult(BookingOutcome.NOT_OPEN_YET, "group not bookable yet")

            # BOOKABLE
            return self._attempt_booking(client, slot, group.booking_path)

    def _attempt_booking(self, client: httpx.Client, slot: Slot, booking_path: str | None) -> BookingResult:
        if not booking_path:  # pragma: no cover - defensive, BOOKABLE always carries a path
            logger.error("Group %s is BOOKABLE but has no booking link", slot.group_code)
            return BookingResult(BookingOutcome.ERROR, "bookable group has no booking link")

        booking_url = urljoin(self._base_url, booking_path)
        response, error = self._get(client, booking_url)
        if error is not None:
            return error

        groups = parse_groups(response.text)
        group = groups.get(slot.group_code)

        if group is not None and group.state is GroupState.ENROLLED:
            logger.info("Booked group %s", slot.group_code)
            return BookingResult(BookingOutcome.BOOKED)

        if group is not None and group.state is GroupState.FULL:
            logger.info("Group %s became full while booking", slot.group_code)
            return BookingResult(BookingOutcome.TAKEN)

        logger.warning(
            "Unexpected state for group %s after booking attempt: %s",
            slot.group_code,
            group.state if group is not None else "missing",
        )
        return BookingResult(BookingOutcome.ERROR, "unexpected state after booking attempt")

    def _get(self, client: httpx.Client, url: str) -> tuple[httpx.Response | None, BookingResult | None]:
        """GET `url`, classifying the outcome. Never raises."""
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("Request to UPV failed: %s", exc)
            return None, BookingResult(BookingOutcome.ERROR, str(exc))

        if httpx.URL(str(response.url)).host == self._cas_host:
            logger.info("Session expired (redirected to CAS)")
            return None, BookingResult(BookingOutcome.SESSION_EXPIRED)

        if response.status_code >= 500:
            logger.warning("UPV returned HTTP %d for %s", response.status_code, url)
            return None, BookingResult(BookingOutcome.ERROR, f"HTTP {response.status_code}")

        response.encoding = RESPONSE_ENCODING
        return response, None
