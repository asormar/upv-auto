"""Turn-taking coordination for the multi-user batch (weekly-batch-booking spec).

`BookSlotUseCase` is reused untouched per user (design.md's "Batch execution"
decision): each user runs in its own thread, and `TurnScheduler` plus
`TurnTakingClock` make sure at most one user's thread is ever doing UPV work
at a time, without `BookSlotUseCase` knowing turn-taking exists at all.

How it works: a user's thread holds the turn (an exclusive lock, handed out
in fair rotation order) for as long as it is doing real work — logging in,
fetching the table, following a booking link. The only place `BookSlotUseCase`
ever gives up control is `Clock.sleep()` (waiting for the window to open, or
for a retry round). `TurnTakingClock.sleep()` is where the turn is released:
it moves this user to the back of the rotation, actually waits out the
requested duration, then blocks until it is this user's turn again. That is
exactly what "a retrying user does not starve the others" requires: it never
jumps the queue just because it woke up first.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime

from upv_auto.ports import Clock


class TurnScheduler:
    """Fair round-robin turn coordinator: at most one registered user's turn is active.

    Users are registered up front, in rotation order. `acquire(user_id)`
    blocks until this user is at the front of the rotation. `yield_turn`
    rotates this user to the back (it wants another turn later).
    `finish` removes this user from the rotation entirely (it is done for
    the whole run) and never blocks anyone on it again.
    """

    def __init__(self, user_ids: list[str]) -> None:
        self._condition = threading.Condition()
        self._order: deque[str] = deque(user_ids)

    def acquire(self, user_id: str) -> None:
        with self._condition:
            self._condition.wait_for(lambda: self._front() == user_id)

    def yield_turn(self, user_id: str) -> None:
        with self._condition:
            if self._order and self._order[0] == user_id:
                self._order.rotate(-1)
            self._condition.notify_all()

    def finish(self, user_id: str) -> None:
        with self._condition:
            if user_id in self._order:
                self._order.remove(user_id)
            self._condition.notify_all()

    def _front(self) -> str | None:
        return self._order[0] if self._order else None


class TurnTakingClock:
    """A `Clock` that hands off the turn every time it sleeps.

    `now()` reads the shared underlying clock directly — wall-clock time is
    common to every user, so no turn is needed to read it. `sleep()` yields
    this user's turn before waiting (so whoever is next in rotation is not
    blocked on this user's retry), waits out the real/virtual duration on the
    shared clock, then re-acquires the turn — in fair rotation order — before
    returning control to `BookSlotUseCase`.
    """

    def __init__(self, user_id: str, scheduler: TurnScheduler, clock: Clock) -> None:
        self._user_id = user_id
        self._scheduler = scheduler
        self._clock = clock

    def now(self) -> datetime:
        return self._clock.now()

    def sleep(self, seconds: float) -> None:
        self._scheduler.yield_turn(self._user_id)
        self._clock.sleep(seconds)
        self._scheduler.acquire(self._user_id)


class BufferedNotifier:
    """Buffers `notify()` calls instead of sending them immediately.

    Used per user during the batch: SMTP must stay out of the turn-taking
    window (design.md's "Notification" decision), so each user's outcome is
    buffered here, and the real send happens once, after every thread has
    joined — see `app.run_batch`.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, text: str) -> None:
        self.messages.append(text)

    def combined(self) -> str:
        """All buffered messages, most recent last, joined for a single email."""
        return "\n\n".join(self.messages)
