"""Tests for the turn-taking primitives (weekly-batch-booking spec:
"Turn-Taking Multi-User Run", "A retrying user does not starve the others").
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from fakes import FakeClock

from upv_auto.app.turns import BufferedNotifier, TurnScheduler, TurnTakingClock

START = datetime(2024, 1, 6, 10, 0, 0)


# -- TurnScheduler: fair rotation, no real threads needed to test the FIFO logic ------


def test_acquire_returns_immediately_for_the_user_already_at_the_front():
    scheduler = TurnScheduler(["u1", "u2", "u3"])

    scheduler.acquire("u1")  # does not block: u1 is at the front


def test_yield_turn_rotates_to_the_back_and_a_retrying_user_does_not_starve_others():
    scheduler = TurnScheduler(["u1", "u2", "u3"])
    order: list[str] = []

    # u1 takes its turn, then needs to retry (yields).
    scheduler.acquire("u1")
    order.append("u1")
    scheduler.yield_turn("u1")

    # u2 and u3 must get their turn before u1 retries — this is the scenario
    # "A retrying user does not starve the others" from weekly-batch-booking.md.
    scheduler.acquire("u2")
    order.append("u2")
    scheduler.yield_turn("u2")

    scheduler.acquire("u3")
    order.append("u3")
    scheduler.yield_turn("u3")

    scheduler.acquire("u1")
    order.append("u1")

    assert order == ["u1", "u2", "u3", "u1"]


def test_finish_removes_a_user_from_the_rotation_permanently():
    scheduler = TurnScheduler(["u1", "u2"])

    scheduler.acquire("u1")
    scheduler.finish("u1")  # u1 is done for the whole run

    scheduler.acquire("u2")
    scheduler.yield_turn("u2")
    # With u1 gone, u2 is the only one left: it gets the turn back immediately.
    scheduler.acquire("u2")


# -- TurnScheduler: real concurrency, mutual exclusion ---------------------------------


def test_only_one_user_holds_the_turn_at_any_instant():
    """`TurnScheduler` keeps exactly one active user (weekly-batch-booking spec)."""
    user_ids = ["u1", "u2", "u3"]
    scheduler = TurnScheduler(user_ids)
    lock = threading.Lock()
    active: set[str] = set()
    max_concurrent = [0]
    rounds_per_user = 4

    def worker(user_id: str) -> None:
        for _ in range(rounds_per_user):
            scheduler.acquire(user_id)
            with lock:
                active.add(user_id)
                max_concurrent[0] = max(max_concurrent[0], len(active))
            time.sleep(0.005)  # simulated UPV work while holding the turn
            with lock:
                active.discard(user_id)
            scheduler.yield_turn(user_id)
        scheduler.finish(user_id)

    threads = [threading.Thread(target=worker, args=(uid,)) for uid in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert max_concurrent[0] == 1


# -- TurnTakingClock --------------------------------------------------------------------


def test_sleep_yields_the_turn_before_waiting_and_reacquires_it_after():
    scheduler = TurnScheduler(["u1", "u2"])
    clock = FakeClock(START)
    turn_clock_1 = TurnTakingClock("u1", scheduler, clock)

    def u2_worker() -> None:
        # Simulates u2's own loop: takes its turn, then gives it back (to u1).
        scheduler.acquire("u2")
        scheduler.yield_turn("u2")

    scheduler.acquire("u1")
    thread = threading.Thread(target=u2_worker)
    thread.start()

    turn_clock_1.sleep(5.0)  # releases u1's turn, lets u2 run, then blocks until u1's turn again
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert clock.sleep_calls == [5.0]
    assert clock.now() == START + timedelta(seconds=5)


def test_now_reads_the_shared_underlying_clock():
    scheduler = TurnScheduler(["u1"])
    clock = FakeClock(START)
    turn_clock = TurnTakingClock("u1", scheduler, clock)

    assert turn_clock.now() == START


def test_a_second_user_gets_its_turn_while_the_first_sleeps():
    scheduler = TurnScheduler(["u1", "u2"])
    clock = FakeClock(START)
    turn_clock_1 = TurnTakingClock("u1", scheduler, clock)

    u2_got_turn = threading.Event()

    def u2_worker() -> None:
        scheduler.acquire("u2")
        u2_got_turn.set()
        scheduler.finish("u2")

    scheduler.acquire("u1")
    thread = threading.Thread(target=u2_worker)
    thread.start()

    # While u1 sleeps, it yields, letting u2's thread acquire the turn.
    turn_clock_1.sleep(1.0)

    thread.join(timeout=5)
    assert u2_got_turn.is_set()


# -- BufferedNotifier ---------------------------------------------------------------------


def test_buffered_notifier_buffers_instead_of_sending():
    notifier = BufferedNotifier()

    notifier.notify("first message")
    notifier.notify("second message")

    assert notifier.messages == ["first message", "second message"]
    assert notifier.combined() == "first message\n\nsecond message"


def test_buffered_notifier_combined_is_empty_for_no_messages():
    notifier = BufferedNotifier()

    assert notifier.combined() == ""
