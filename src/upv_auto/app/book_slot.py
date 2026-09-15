"""Use case: wait for the booking window and secure every configured booking.

Algorithm:
1. Log in and verify the session, retrying transient failures (see
   `authenticate`); on failure, notify and stop (exit code 1).
2. Wait until the window opens (coarse sleep while more than 5s remain, then
   fine 50ms steps). With `skip_wait` (testing), the window opens immediately
   and keeps its configured length.
3. Until the window closes, go round-robin over every pending booking target,
   trying its current group (preferred first, then alternatives):
   - BOOKED -> that target is done.
   - TAKEN -> move that target to its next alternative; none left -> done, failed.
   - NOT_OPEN_YET / ERROR -> retry next round, after `retry_interval_seconds`.
   - ALREADY_ENROLLED -> also retried, never counted as success: the page has no
     week indicator and may still show the previous week's enrolments.
   - SESSION_EXPIRED -> re-login at most once; a second expiry gives up (1).
   - NotImplementedError from the booking client -> notify and stop (1).
4. Send one summary notification. Exit 0 only if every target was booked.
"""

from __future__ import annotations

import logging
from datetime import datetime

from upv_auto.app.authenticate import authenticate
from upv_auto.config import AppConfig
from upv_auto.domain.models import BookingOutcome, BookingTarget, BookingWindow, Session, Slot
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

        if skip_wait:
            # Testing outside the real schedule: open the window now, same length.
            now = self._clock.now()
            window = BookingWindow(
                opens_at=now,
                closes_at=now + (window.closes_at - window.opens_at),
                retry_interval_seconds=window.retry_interval_seconds,
            )
        else:
            self._wait_until(window.opens_at)

        return self._book_loop(session, window)

    # -- steps -----------------------------------------------------------

    def _login_and_verify(self) -> Session | None:
        return authenticate(
            self._config.credentials,
            self._authenticator,
            self._verifier,
            self._notifier,
            self._clock,
        )

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
        """Round-robin over every booking target so none waits for another to finish."""
        pending = [_TargetProgress(target) for target in self._config.bookings]
        finished: list[_TargetProgress] = []
        attempts = 0
        relogin_used = False

        while pending and self._clock.now() < window.closes_at:
            needs_retry = False

            for progress in list(pending):
                slot = progress.current_slot
                attempts += 1
                try:
                    result = self._booking_client.book(session, slot)
                except NotImplementedError as exc:
                    logger.error("Booking adapter not implemented: %s", exc)
                    self._notifier.notify(f"Booking adapter not implemented yet: {exc}")
                    return 1

                if result.outcome is BookingOutcome.BOOKED:
                    logger.info("Booked %s after %d total attempt(s)", slot.label, attempts)
                    progress.booked = slot
                elif result.outcome is BookingOutcome.TAKEN:
                    logger.info("Group %s is taken", slot.label)
                    progress.index += 1
                elif result.outcome is BookingOutcome.SESSION_EXPIRED:
                    if relogin_used:
                        logger.error("Session expired again after re-login; giving up")
                        self._notifier.notify(
                            self._summary(finished + pending, "Session expired again after re-login. Giving up.")
                        )
                        return 1
                    relogin_used = True
                    logger.info("Session expired, re-authenticating")
                    new_session = self._login_and_verify()
                    if new_session is None:
                        return 1
                    session = new_session
                    break  # restart the round with the fresh session
                else:
                    # NOT_OPEN_YET, ERROR or ALREADY_ENROLLED: retry next round. An existing
                    # enrolment may belong to the previous week's table, not yet refreshed.
                    if result.outcome is BookingOutcome.ALREADY_ENROLLED:
                        progress.seen_enrolled = True
                    needs_retry = True

                if progress.is_finished:
                    pending.remove(progress)
                    finished.append(progress)

            if pending and needs_retry:
                self._clock.sleep(window.retry_interval_seconds)

        closed_note = "" if not pending else f"Booking window closed after {attempts} attempt(s)."
        self._notifier.notify(self._summary(finished + pending, closed_note))
        logger.info("Booking finished after %d attempt(s)", attempts)
        return 0 if all(p.booked for p in finished + pending) else 1

    @staticmethod
    def _summary(progresses: list[_TargetProgress], note: str) -> str:
        booked = [p for p in progresses if p.booked]
        lines = [f"Booked {len(booked)}/{len(progresses)}: " + (", ".join(p.booked.label for p in booked) or "none")]
        for progress in progresses:
            if progress.booked:
                lines.append(f"- {progress.target.label}: booked {progress.booked.label}")
            elif progress.is_finished:
                lines.append(f"- {progress.target.label}: all groups taken")
            elif progress.seen_enrolled:
                lines.append(
                    f"- {progress.target.label}: not booked; it kept showing as already enrolled "
                    "(the table may not have refreshed to next week). Check manually."
                )
            else:
                lines.append(f"- {progress.target.label}: not booked")
        if note:
            lines.append(note)
        return "\n".join(lines)


class _TargetProgress:
    def __init__(self, target: BookingTarget) -> None:
        self.target = target
        self.index = 0
        self.booked: Slot | None = None
        self.seen_enrolled = False

    @property
    def current_slot(self) -> Slot:
        return self.target.options[self.index]

    @property
    def is_finished(self) -> bool:
        return self.booked is not None or self.index >= len(self.target.options)
