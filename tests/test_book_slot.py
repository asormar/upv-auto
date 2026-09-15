from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeActivityTableClient, FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier, error, expired, table

from upv_auto.app.book_slot import BookSlotUseCase
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
