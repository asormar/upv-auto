"""Use case: wait for the booking window and secure every configured booking.

Algorithm:
1. Log in and verify the session, retrying transient failures (see
   `authenticate`); on failure, notify and stop (exit code 1).
2. Wait until the window opens (coarse sleep while more than 5s remain, then
   fine 50ms steps). With `skip_wait` (testing), the window opens immediately
   and keeps its configured length.
3. Until the window closes, run rounds. Each round downloads the activity
   table exactly once (`fetch_groups`) and then goes round-robin over every
   pending booking target, resolving its current group (preferred first,
   then alternatives) against that one table:
   - BOOKABLE -> follow the scraped booking link (`follow_booking`). UPV
     redirects that request back to the refreshed table, so its response
     replaces the table for the rest of the round — the remaining targets
     in this round are resolved against it too, with no extra download.
   - FULL -> move to the next alternative and re-evaluate it immediately
     against the same table; no alternatives left -> that target is done,
     failed.
   - ENROLLED -> the page has no week indicator, so this may still be last
     week's table. Only counted as booked if this run already followed a
     booking link for that exact code (a booking GET that may have timed
     out but succeeded server-side); otherwise it is retried next round.
   - missing / UNAVAILABLE -> retried next round.
   - SESSION_EXPIRED (from either call) -> re-login at most once for the
     whole run; a second expiry gives up (1). A successful re-login ends
     the round early so the next one refetches from scratch.
   If any pending target still needs a retry after the round, sleep
   `retry_interval_seconds` once (not once per target).
4. Send one summary notification. Exit 0 only if every target was booked.
"""

from __future__ import annotations

import logging
from datetime import datetime

from upv_auto.app.authenticate import authenticate
from upv_auto.config import AppConfig
from upv_auto.domain.models import BookingOutcome, BookingTarget, BookingWindow, GroupState, Session, Slot
from upv_auto.ports import ActivityTableClient, Authenticator, Clock, Notifier, SessionVerifier

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
        table_client: ActivityTableClient,
        notifier: Notifier,
        clock: Clock,
        config: AppConfig,
    ) -> None:
        self._authenticator = authenticator
        self._verifier = verifier
        self._table_client = table_client
        self._notifier = notifier
        self._clock = clock
        self._config = config

    def execute(self, *, skip_wait: bool = False) -> int:
        if not self._config.bookings:
            logger.info("Nothing queued: no booking to make")
            self._notifier.notify("Nothing queued for this run.")
            return 0

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
        """Round-robin over every pending target, downloading the table once per round."""
        pending = [_TargetProgress(target) for target in self._config.bookings]
        finished: list[_TargetProgress] = []
        attempts = 0
        relogin_used = False

        while pending and self._clock.now() < window.closes_at:
            snapshot = self._table_client.fetch_groups(session)
            attempts += 1

            if snapshot.failure is BookingOutcome.SESSION_EXPIRED:
                session, relogin_used, gave_up = self._reauthenticate(relogin_used, finished, pending)
                if gave_up:
                    return 1
                continue  # refetch immediately with the fresh session, no sleep

            if snapshot.failure is BookingOutcome.ERROR:
                self._clock.sleep(window.retry_interval_seconds)
                continue

            groups = snapshot.groups
            needs_retry = False
            interrupted = False

            for progress in list(pending):
                just_followed = False

                while True:
                    slot = progress.current_slot
                    group = groups.get(slot.group_code)

                    if group is None or group.state is GroupState.UNAVAILABLE:
                        needs_retry = True
                        break

                    if group.state is GroupState.ENROLLED:
                        if slot.group_code in progress.attempted_codes:
                            logger.info("Booked %s after %d total attempt(s)", slot.label, attempts)
                            progress.booked = slot
                        else:
                            # The page has no week indicator: this enrolment may
                            # belong to last week's table, not something we did.
                            progress.seen_enrolled = True
                            needs_retry = True
                        break

                    if group.state is GroupState.FULL:
                        logger.info("Group %s is full", slot.label)
                        progress.index += 1
                        just_followed = False
                        if progress.is_finished:
                            break
                        continue  # re-evaluate the new alternative against the same table

                    if just_followed:
                        # Unexpected: still bookable right after following its own link.
                        needs_retry = True
                        break

                    # BOOKABLE
                    progress.attempted_codes.add(slot.group_code)
                    attempts += 1
                    after = self._table_client.follow_booking(session, group)

                    if after.failure is BookingOutcome.SESSION_EXPIRED:
                        session, relogin_used, gave_up = self._reauthenticate(relogin_used, finished, pending)
                        if gave_up:
                            return 1
                        interrupted = True
                        break

                    if after.failure is BookingOutcome.ERROR:
                        needs_retry = True
                        break

                    groups = after.groups  # fresh table, reused by the rest of this round
                    just_followed = True

                if progress.is_finished:
                    pending.remove(progress)
                    finished.append(progress)

                if interrupted:
                    break  # this round ends here; the next one refetches from scratch

            if interrupted:
                continue

            if pending and needs_retry:
                self._clock.sleep(window.retry_interval_seconds)

        closed_note = "" if not pending else f"Booking window closed after {attempts} attempt(s)."
        self._notifier.notify(self._summary(finished + pending, closed_note))
        logger.info("Booking finished after %d attempt(s)", attempts)
        return 0 if all(p.booked for p in finished + pending) else 1

    def _reauthenticate(
        self,
        relogin_used: bool,
        finished: list[_TargetProgress],
        pending: list[_TargetProgress],
    ) -> tuple[Session | None, bool, bool]:
        """Handle a SESSION_EXPIRED failure.

        Returns `(session, relogin_used, gave_up)`. At most one re-login is
        allowed for the whole run: a second expiry notifies a summary and
        gives up. A re-login that itself fails also gives up, without an
        extra summary (`authenticate` already notified why).
        """
        if relogin_used:
            logger.error("Session expired again after re-login; giving up")
            self._notifier.notify(
                self._summary(finished + pending, "Session expired again after re-login. Giving up.")
            )
            return None, relogin_used, True

        logger.info("Session expired, re-authenticating")
        new_session = self._login_and_verify()
        if new_session is None:
            return None, relogin_used, True
        return new_session, True, False

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
        self.attempted_codes: set[str] = set()

    @property
    def current_slot(self) -> Slot:
        return self.target.options[self.index]

    @property
    def is_finished(self) -> bool:
        return self.booked is not None or self.index >= len(self.target.options)
