"""Booking HTTP adapter — STUB.

The real UPV booking endpoints (URLs, request payloads, response shapes) are
not mapped yet. This adapter exists so the rest of the application (the
retry loop, notifications, CLI, tests) can be wired and exercised end to end.

Once the endpoints are known (inspect the booking flow's network traffic
while authenticated), replace the body of `book()` with real httpx calls
against `upv_auto.adapters.httpx_session.build_client(session)`, and map the
site's responses onto `BookingOutcome` (BOOKED, NOT_OPEN_YET, TAKEN,
SESSION_EXPIRED, ERROR).
"""

from __future__ import annotations

from upv_auto.domain.models import BookingResult, Session, Slot


class HttpxBookingClient:
    def book(self, session: Session, slot: Slot) -> BookingResult:
        raise NotImplementedError(
            "Booking endpoints not mapped yet. Inspect the UPV booking flow "
            "(browser network tab, while logged in) and implement "
            "HttpxBookingClient.book() before running this against real slots."
        )
