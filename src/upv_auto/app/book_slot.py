"""Use case: wait for the booking window and attempt to book a slot.

Algorithm:
1. Log in and verify the session; on failure, notify and stop (exit code 1).
2. Wait until the window opens (coarse sleep while more than 5s remain, then
   fine 50ms steps), unless `skip_wait` is set (used for local testing).
3. Loop until the window closes, trying the current slot (preferred first,
   then alternatives in configured order):
   - BOOKED -> notify success, stop (0).
   - TAKEN -> advance to the next slot; if none are left, notify and stop (1).
   - NOT_OPEN_YET / ERROR -> sleep `retry_interval_seconds`, retry the same slot.
   - SESSION_EXPIRED -> re-login at most once; a second expiry gives up (1).
   - NotImplementedError from the booking client -> notify and stop (1)
     immediately, without retrying (the adapter is not wired to a real
     endpoint yet, so retrying would just spin).
4. If the window closes without success, notify a timeout with the attempt count.
"""

from __future__ import annotations

import logging
from datetime import datetime

from upv_auto.config import AppConfig
from upv_auto.domain.errors import AuthenticationBlocked, AuthenticationFailed
from upv_auto.domain.models import BookingOutcome, BookingWindow, Session
from upv_auto.ports import Authenticator, BookingClient, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)

# While more than this many seconds remain before the window opens, sleep in
# coarse chunks; below it, switch to fine-grained polling.
_COARSE_THRESHOLD_SECONDS = 5.0
_FINE_STEP_SECONDS = 0.05


class BookSlotUseCase:
    def __init__(
        self,
        authenticator: Authenticator,
        verifier: SessionVerifier,
        booking_client: BookingClient,
        notifier: Notifier,
        clock: Clock,
        config: AppConfig,
    ) -> None:
        self._authenticator = authenticator
        self._verifier = verifier
        self._booking_client = booking_client
        self._notifier = notifier
        self._clock = clock
        self._config = config

    def execute(self, *, skip_wait: bool = False) -> int:
        session = self._login_and_verify()
        if session is None:
            return 1

        window = self._compute_window()

        if not skip_wait:
            self._wait_until(window.opens_at)

        return self._book_loop(session, window)

    # -- steps -----------------------------------------------------------

    def _login_and_verify(self) -> Session | None:
        try:
            session = self._authenticator.login(self._config.credentials)
        except AuthenticationBlocked as exc:
            logger.warning("Login blocked: %s", exc)
            self._notifier.notify(f"Login blocked (captcha/2FA/unexpected page): {exc}")
            return None
        except AuthenticationFailed as exc:
            logger.warning("Login failed: %s", exc)
            self._notifier.notify(f"Login failed: {exc}")
            return None

        if not self._verifier.is_valid(session):
            logger.warning("Session verification failed after login")
            self._notifier.notify("Login appeared to succeed but session verification failed.")
            return None

        return session

    def _compute_window(self) -> BookingWindow:
        now = self._clock.now()
        return BookingWindow(
            opens_at=self._combine(now, self._config.window.opens_at),
            closes_at=self._combine(now, self._config.window.closes_at),
            retry_interval_seconds=self._config.window.retry_interval_seconds,
        )

    @staticmethod
    def _combine(reference: datetime, time_str: str) -> datetime:
        hour, minute, second = (int(part) for part in time_str.split(":"))
        return reference.replace(hour=hour, minute=minute, second=second, microsecond=0)

    def _wait_until(self, target: datetime) -> None:
        while True:
            remaining = (target - self._clock.now()).total_seconds()
            if remaining <= 0:
                return
            if remaining > _COARSE_THRESHOLD_SECONDS:
                self._clock.sleep(remaining - _COARSE_THRESHOLD_SECONDS)
            else:
                self._clock.sleep(_FINE_STEP_SECONDS)

    def _book_loop(self, session: Session, window: BookingWindow) -> int:
        slots = list(self._config.slots)
        slot_index = 0
        attempts = 0
        relogin_used = False

        while self._clock.now() < window.closes_at:
            if slot_index >= len(slots):
                logger.info("All configured slots are taken")
                self._notifier.notify("All configured slots are taken. Booking failed.")
                return 1

            slot = slots[slot_index]

            try:
                attempts += 1
                result = self._booking_client.book(session, slot)
            except NotImplementedError as exc:
                logger.error("Booking adapter not implemented: %s", exc)
                self._notifier.notify(f"Booking adapter not implemented yet: {exc}")
                return 1

            if result.outcome is BookingOutcome.BOOKED:
                logger.info("Booked %s after %d attempt(s)", slot.label, attempts)
                self._notifier.notify(f"Booked slot {slot.label} after {attempts} attempt(s).")
                return 0

            if result.outcome is BookingOutcome.TAKEN:
                logger.info("Slot %s is taken, trying next alternative", slot.label)
                slot_index += 1
                continue

            if result.outcome is BookingOutcome.SESSION_EXPIRED:
                if relogin_used:
                    logger.error("Session expired again after re-login; giving up")
                    self._notifier.notify("Session expired again after re-login. Giving up.")
                    return 1
                relogin_used = True
                logger.info("Session expired, re-authenticating")
                new_session = self._login_and_verify()
                if new_session is None:
                    return 1
                session = new_session
                continue

            # NOT_OPEN_YET or ERROR: retry the same slot after the configured interval.
            self._clock.sleep(window.retry_interval_seconds)

        logger.info("Booking window closed after %d attempt(s)", attempts)
        self._notifier.notify(f"Booking window closed after {attempts} attempt(s) without success.")
        return 1
