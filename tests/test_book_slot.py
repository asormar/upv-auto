from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeActivityTableClient, FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier, error, expired, sanctioned, table

from upv_auto.app.book_slot import _MAX_CONSECUTIVE_REFUSALS, _MAX_MISSING_ROUNDS, BookSlotUseCase
from upv_auto.config import AppConfig, UpvConfig, WindowConfig
from upv_auto.domain.errors import AuthenticationFailed
from upv_auto.domain.models import Activity, BookingTarget, Credentials, Slot

TZ = ZoneInfo("Europe/Madrid")

SLOT_A = Slot(group_code="MUS074")
SLOT_B = Slot(group_code="MUS075")
SLOT_C = Slot(group_code="MUS037")


def make_config(
    *,
    bookings: list[BookingTarget],
    retry_interval_seconds: float = 1.5,
) -> AppConfig:
    return AppConfig(
        timezone="Europe/Madrid",
        upv=UpvConfig(entry_url="https://example.test/entry", session_check_url="https://example.test/entry"),
        window=WindowConfig(
            weekday="saturday",
            opens_at="10:00:00",
            closes_at="10:03:00",
            retry_interval_seconds=retry_interval_seconds,
        ),
        activity=Activity(campus="V", tipoact="6894", codacti="21948", name="MUSCULACION"),
        bookings=bookings,
        credentials=Credentials(username="user", password="secret"),
        email=None,
    )


def build_use_case(
    *,
    config: AppConfig,
    clock: FakeClock,
    table_client: FakeActivityTableClient,
    authenticator: FakeAuthenticator | None = None,
) -> tuple[BookSlotUseCase, FakeNotifier, FakeAuthenticator]:
    authenticator = authenticator or FakeAuthenticator()
    verifier = FakeVerifier(valid=True)
    notifier = FakeNotifier()
    use_case = BookSlotUseCase(
        authenticator=authenticator,
        verifier=verifier,
        table_client=table_client,
        notifier=notifier,
        clock=clock,
        config=config,
    )
    return use_case, notifier, authenticator


def fetch_calls(table_client: FakeActivityTableClient) -> int:
    return sum(1 for call in table_client.calls if call == ("fetch",))


def test_waits_until_open_then_retries_not_open_yet_before_booking():
    config = make_config(bookings=[BookingTarget((SLOT_A,))], retry_interval_seconds=1.5)
    start = datetime(2024, 1, 6, 9, 59, 50, tzinfo=TZ)  # 10s before opens_at
    clock = FakeClock(start)
    table_client = FakeActivityTableClient(
        fetch_results=[table(), table(MUS074="BOOKABLE")],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=False)

    assert result == 0
    assert fetch_calls(table_client) == 2
    assert table_client.calls[-1] == ("follow", "MUS074")
    assert clock.sleep_calls, "expected the use case to wait for the window to open"
    assert clock.now() >= datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    assert any("Booked" in m for m in notifier.messages)


def test_full_moves_to_next_alternative_within_the_same_round():
    config = make_config(bookings=[BookingTarget((SLOT_A, SLOT_B))])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="FULL", MUS075="BOOKABLE")],
        follow_results={"MUS075": [table(MUS074="FULL", MUS075="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert fetch_calls(table_client) == 1  # no extra download to resolve the alternative
    assert table_client.calls == [("fetch",), ("follow", "MUS075")]
    assert any("Booked" in m for m in notifier.messages)


def test_all_slots_full_reports_failure():
    config = make_config(bookings=[BookingTarget((SLOT_A, SLOT_B))])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    table_client = FakeActivityTableClient(fetch_results=[table(MUS074="FULL", MUS075="FULL")])
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert fetch_calls(table_client) == 1
    assert any("taken" in m.lower() for m in notifier.messages)


def test_window_timeout_reports_failure_after_closing():
    config = make_config(bookings=[BookingTarget((SLOT_A,))], retry_interval_seconds=1.0)
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)  # exactly at opens_at
    clock = FakeClock(start)
    # window closes at 10:03:00 -> 180s / 1.0s retry -> up to 180 rounds.
    table_client = FakeActivityTableClient(fetch_results=[table() for _ in range(200)])
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert clock.now() >= datetime(2024, 1, 6, 10, 3, 0, tzinfo=TZ)
    assert any("closed" in m.lower() for m in notifier.messages)


def test_session_expired_triggers_exactly_one_relogin_then_succeeds():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator()
    table_client = FakeActivityTableClient(
        fetch_results=[expired(), table(MUS074="BOOKABLE")],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, authenticator = build_use_case(
        config=config, clock=clock, table_client=table_client, authenticator=authenticator
    )

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert authenticator.calls == 2  # initial login + exactly one re-login
    assert any("Booked" in m for m in notifier.messages)


def test_session_expired_twice_gives_up_after_one_relogin():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator()
    table_client = FakeActivityTableClient(fetch_results=[expired(), expired()])
    use_case, notifier, authenticator = build_use_case(
        config=config, clock=clock, table_client=table_client, authenticator=authenticator
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert authenticator.calls == 2  # initial login + exactly one re-login, no more
    assert fetch_calls(table_client) == 2
    assert any("giving up" in m.lower() or "expired" in m.lower() for m in notifier.messages)


def test_login_failure_exits_without_attempting_to_book():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator(error=AuthenticationFailed("bad credentials"))
    table_client = FakeActivityTableClient(fetch_results=[])
    use_case, notifier, _ = build_use_case(
        config=config, clock=clock, table_client=table_client, authenticator=authenticator
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert table_client.calls == []
    assert any("Login failed" in m for m in notifier.messages)
    assert not any("secret" in m for m in notifier.messages)


def test_skip_wait_outside_schedule_still_gets_a_full_retry_window():
    config = make_config(bookings=[BookingTarget((SLOT_A,))], retry_interval_seconds=1.0)
    start = datetime(2024, 1, 6, 16, 45, 0, tzinfo=TZ)  # hours after the configured window
    clock = FakeClock(start)
    table_client = FakeActivityTableClient(
        fetch_results=[table(), table(MUS074="BOOKABLE")],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert fetch_calls(table_client) == 2


def test_books_every_target_with_exactly_one_fetch_per_round():
    config = make_config(bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="BOOKABLE", MUS075="BOOKABLE")],
        follow_results={
            "MUS074": [table(MUS074="ENROLLED", MUS075="BOOKABLE")],
            "MUS075": [table(MUS074="ENROLLED", MUS075="ENROLLED")],
        },
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert fetch_calls(table_client) == 1  # the second target reused follow_booking's table
    assert table_client.calls == [("fetch",), ("follow", "MUS074"), ("follow", "MUS075")]
    assert notifier.messages[-1].startswith("Booked 2/2: MUS074, MUS075")


def test_targets_are_tried_round_robin_and_sleep_once_per_round():
    config = make_config(bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(), table(MUS074="BOOKABLE", MUS075="BOOKABLE")],
        follow_results={
            "MUS074": [table(MUS074="ENROLLED", MUS075="BOOKABLE")],
            "MUS075": [table(MUS074="ENROLLED", MUS075="ENROLLED")],
        },
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert clock.sleep_calls == [1.5]  # one pause per round, not per target


def test_partial_success_reports_each_target_and_exits_non_zero():
    config = make_config(bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B, SLOT_C))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="BOOKABLE", MUS075="FULL", MUS037="FULL")],
        follow_results={"MUS074": [table(MUS074="ENROLLED", MUS075="FULL", MUS037="FULL")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    summary = notifier.messages[-1]
    assert summary.startswith("Booked 1/2: MUS074")
    assert "MUS075 (alternatives: MUS037): all groups taken" in summary


def test_already_enrolled_is_retried_until_the_table_refreshes_then_booked():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="ENROLLED"), table(MUS074="BOOKABLE")],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert fetch_calls(table_client) == 2
    assert notifier.messages[-1].startswith("Booked 1/1: MUS074")


def test_already_enrolled_for_the_whole_window_is_not_reported_as_success():
    config = make_config(bookings=[BookingTarget((SLOT_A,))], retry_interval_seconds=60.0)
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(fetch_results=[table(MUS074="ENROLLED") for _ in range(10)])
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    summary = notifier.messages[-1]
    assert summary.startswith("Booked 0/1")
    assert "already enrolled" in summary
    assert "Check manually" in summary


def test_follow_booking_error_then_next_round_confirms_via_attempted_codes():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="BOOKABLE"), table(MUS074="ENROLLED")],
        follow_results={"MUS074": [error("timeout")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert table_client.calls == [("fetch",), ("follow", "MUS074"), ("fetch",)]
    assert notifier.messages[-1].startswith("Booked 1/1: MUS074")


def test_an_empty_queue_never_logs_in():
    authenticator = FakeAuthenticator()
    notifier = FakeNotifier()
    use_case = BookSlotUseCase(
        authenticator=authenticator,
        verifier=FakeVerifier(),
        table_client=FakeActivityTableClient([]),
        notifier=notifier,
        clock=FakeClock(datetime(2026, 9, 19, 10, 0, tzinfo=TZ)),
        config=make_config(bookings=[]),
    )

    exit_code = use_case.execute(skip_wait=True)

    assert exit_code == 0
    assert authenticator.calls == 0
    assert "Nothing queued" in notifier.messages[0]


def test_sanctioned_user_gives_up_at_once_without_retrying():
    config = make_config(bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="BOOKABLE", MUS075="BOOKABLE")],
        follow_results={"MUS074": [sanctioned()]},
    )
    use_case, notifier, authenticator = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert table_client.calls == [("fetch",), ("follow", "MUS074")]  # nothing after the sanction
    assert clock.sleep_calls == []
    assert authenticator.calls == 1  # no re-login
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("Booked 0/2: none")
    assert "sanctioned and cannot book. Stopped retrying." in notifier.messages[0]


def test_consecutive_refusals_give_up_after_exactly_the_limit():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    # UPV keeps answering with the table where the group is still bookable.
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS074="BOOKABLE") for _ in range(10)],
        follow_results={"MUS074": [table(MUS074="BOOKABLE") for _ in range(10)]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    follows = [call for call in table_client.calls if call[0] == "follow"]
    assert len(follows) == _MAX_CONSECUTIVE_REFUSALS == 3
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("Booked 0/1: none")
    assert "refused 3 booking attempts in a row" in notifier.messages[0]
    assert not any("closed" in m.lower() for m in notifier.messages)


def test_moving_to_another_alternative_resets_the_refusal_counter():
    config = make_config(bookings=[BookingTarget((SLOT_A, SLOT_B))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    a_open = table(MUS074="BOOKABLE", MUS075="BOOKABLE")
    a_full = table(MUS074="FULL", MUS075="BOOKABLE")
    table_client = FakeActivityTableClient(
        # Two refusals on MUS074, then it fills up; two more on MUS075 and it gets booked:
        # 4 refusals in total, but never 3 in a row on the same group.
        fetch_results=[a_open, a_open, a_full, a_full, a_full],
        follow_results={
            "MUS074": [a_open, a_open],
            "MUS075": [a_full, a_full, table(MUS074="FULL", MUS075="ENROLLED")],
        },
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert table_client.calls.count(("follow", "MUS074")) == 2
    assert table_client.calls.count(("follow", "MUS075")) == 3
    assert notifier.messages[-1].startswith("Booked 1/1: MUS075")


def test_refusals_are_counted_per_target_not_across_targets():
    config = make_config(
        bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B,)), BookingTarget((SLOT_C,))]
    )
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    all_open = table(MUS074="BOOKABLE", MUS075="BOOKABLE", MUS037="BOOKABLE")
    # The table lags once for every target: each one is refused a single time, then booked.
    table_client = FakeActivityTableClient(
        fetch_results=[all_open, all_open],
        follow_results={
            "MUS074": [all_open, table(MUS074="ENROLLED", MUS075="BOOKABLE", MUS037="BOOKABLE")],
            "MUS075": [all_open, table(MUS074="ENROLLED", MUS075="ENROLLED", MUS037="BOOKABLE")],
            "MUS037": [all_open, table(MUS074="ENROLLED", MUS075="ENROLLED", MUS037="ENROLLED")],
        },
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("Booked 3/3: MUS074, MUS075, MUS037")
    assert "refused" not in notifier.messages[0]


def test_a_full_group_after_a_missing_one_is_not_reported_as_missing():
    config = make_config(bookings=[BookingTarget((SLOT_A, SLOT_B))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(fetch_results=[table(MUS075="FULL") for _ in range(_MAX_MISSING_ROUNDS)])
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert "all groups taken" in notifier.messages[-1]
    assert "not in the UPV table" not in notifier.messages[-1]


def test_a_group_missing_for_the_limit_of_rounds_is_dropped_without_waiting_for_the_window():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    # A non-empty table that simply does not list MUS074 (its weekday is hidden).
    table_client = FakeActivityTableClient(fetch_results=[table(MUS075="FULL") for _ in range(50)])
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert fetch_calls(table_client) == _MAX_MISSING_ROUNDS == 10
    assert clock.now() < datetime(2024, 1, 6, 10, 3, 0, tzinfo=TZ)  # ended early
    assert len(notifier.messages) == 1
    assert "not in the UPV table" in notifier.messages[0]
    assert "all groups taken" not in notifier.messages[0]
    assert "closed" not in notifier.messages[0].lower()


def test_another_target_is_still_booked_while_the_first_one_counts_misses():
    config = make_config(bookings=[BookingTarget((SLOT_A,)), BookingTarget((SLOT_B,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS075="BOOKABLE")] + [table(MUS075="ENROLLED") for _ in range(20)],
        follow_results={"MUS075": [table(MUS075="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert table_client.calls.count(("follow", "MUS075")) == 1
    summary = notifier.messages[-1]
    assert summary.startswith("Booked 1/2: MUS075")
    assert f"- {SLOT_A.label}: not booked; its group is not in the UPV table" in summary


def test_the_missing_counter_resets_when_the_group_shows_up_again():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    missing = table(MUS075="FULL")
    almost = _MAX_MISSING_ROUNDS - 1
    table_client = FakeActivityTableClient(
        fetch_results=[
            *[missing] * almost,
            table(MUS074="UNAVAILABLE"),  # listed again: counter back to zero
            *[missing] * almost,  # 18 misses in total, but never 10 in a row
            table(MUS074="BOOKABLE"),
        ],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert notifier.messages[-1].startswith("Booked 1/1: MUS074")


def test_an_empty_table_is_not_a_miss():
    config = make_config(bookings=[BookingTarget((SLOT_A,))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[*[table() for _ in range(_MAX_MISSING_ROUNDS * 2)], table(MUS074="BOOKABLE")],
        follow_results={"MUS074": [table(MUS074="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert notifier.messages[-1].startswith("Booked 1/1: MUS074")


def test_the_next_alternative_is_tried_after_the_preferred_one_goes_missing():
    config = make_config(bookings=[BookingTarget((SLOT_A, SLOT_B))])
    clock = FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ))
    table_client = FakeActivityTableClient(
        fetch_results=[table(MUS075="BOOKABLE") for _ in range(_MAX_MISSING_ROUNDS)],
        follow_results={"MUS075": [table(MUS075="ENROLLED")]},
    )
    use_case, notifier, _ = build_use_case(config=config, clock=clock, table_client=table_client)

    result = use_case.execute(skip_wait=True)

    assert result == 0
    # The alternative is only booked once the preferred one has been missing 10 rounds.
    assert table_client.calls == [("fetch",)] * _MAX_MISSING_ROUNDS + [("follow", "MUS075")]
    assert notifier.messages[-1].startswith("Booked 1/1: MUS075")
