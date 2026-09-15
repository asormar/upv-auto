from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeAuthenticator, FakeBookingClient, FakeClock, FakeNotifier, FakeVerifier

from upv_auto.app.book_slot import BookSlotUseCase
from upv_auto.config import AppConfig, UpvConfig, WindowConfig
from upv_auto.domain.errors import AuthenticationFailed
from upv_auto.domain.models import Activity, BookingOutcome, BookingResult, Credentials, Slot

TZ = ZoneInfo("Europe/Madrid")

SLOT_A = Slot(group_code="MUS074")
SLOT_B = Slot(group_code="MUS075")


def make_config(slots: list[Slot], *, retry_interval_seconds: float = 1.5) -> AppConfig:
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
        slots=slots,
        credentials=Credentials(username="user", password="secret"),
        email=None,
    )


def build_use_case(
    *,
    config: AppConfig,
    clock: FakeClock,
    outcomes: list,
    authenticator: FakeAuthenticator | None = None,
) -> tuple[BookSlotUseCase, FakeBookingClient, FakeNotifier, FakeAuthenticator]:
    authenticator = authenticator or FakeAuthenticator()
    verifier = FakeVerifier(valid=True)
    booking_client = FakeBookingClient(outcomes)
    notifier = FakeNotifier()
    use_case = BookSlotUseCase(
        authenticator=authenticator,
        verifier=verifier,
        booking_client=booking_client,
        notifier=notifier,
        clock=clock,
        config=config,
    )
    return use_case, booking_client, notifier, authenticator


def test_waits_until_open_then_retries_not_open_yet_before_booking():
    config = make_config([SLOT_A], retry_interval_seconds=1.5)
    start = datetime(2024, 1, 6, 9, 59, 50, tzinfo=TZ)  # 10s before opens_at
    clock = FakeClock(start)
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.NOT_OPEN_YET), BookingResult(BookingOutcome.BOOKED)],
    )

    result = use_case.execute(skip_wait=False)

    assert result == 0
    assert len(booking_client.calls) == 2
    assert booking_client.calls[0][1] == SLOT_A
    assert clock.sleep_calls, "expected the use case to wait for the window to open"
    assert clock.now() >= datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    assert any("Booked" in m for m in notifier.messages)


def test_taken_moves_to_next_alternative_slot():
    config = make_config([SLOT_A, SLOT_B])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.TAKEN), BookingResult(BookingOutcome.BOOKED)],
    )

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert [call[1] for call in booking_client.calls] == [SLOT_A, SLOT_B]
    assert any("Booked" in m for m in notifier.messages)


def test_all_slots_taken_reports_failure():
    config = make_config([SLOT_A, SLOT_B])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.TAKEN), BookingResult(BookingOutcome.TAKEN)],
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert len(booking_client.calls) == 2
    assert any("taken" in m.lower() for m in notifier.messages)


def test_window_timeout_reports_failure_after_closing():
    config = make_config([SLOT_A], retry_interval_seconds=1.0)
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)  # exactly at opens_at
    clock = FakeClock(start)
    # window closes at 10:03:00 -> 180s / 1.0s retry -> up to 180 attempts.
    outcomes = [BookingResult(BookingOutcome.NOT_OPEN_YET) for _ in range(200)]
    use_case, booking_client, notifier, _ = build_use_case(config=config, clock=clock, outcomes=outcomes)

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert clock.now() >= datetime(2024, 1, 6, 10, 3, 0, tzinfo=TZ)
    assert any("closed" in m.lower() for m in notifier.messages)


def test_session_expired_triggers_exactly_one_relogin_then_succeeds():
    config = make_config([SLOT_A])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator()
    use_case, booking_client, notifier, authenticator = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.SESSION_EXPIRED), BookingResult(BookingOutcome.BOOKED)],
        authenticator=authenticator,
    )

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert authenticator.calls == 2  # initial login + exactly one re-login
    assert any("Booked" in m for m in notifier.messages)


def test_session_expired_twice_gives_up_after_one_relogin():
    config = make_config([SLOT_A])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator()
    use_case, booking_client, notifier, authenticator = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.SESSION_EXPIRED), BookingResult(BookingOutcome.SESSION_EXPIRED)],
        authenticator=authenticator,
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert authenticator.calls == 2  # initial login + exactly one re-login, no more
    assert len(booking_client.calls) == 2
    assert any("giving up" in m.lower() or "expired" in m.lower() for m in notifier.messages)


def test_not_implemented_booking_client_exits_without_spinning():
    config = make_config([SLOT_A])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[NotImplementedError("stub adapter")],
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert len(booking_client.calls) == 1
    assert clock.sleep_calls == []
    assert any("not implemented" in m.lower() for m in notifier.messages)


def test_login_failure_exits_without_attempting_to_book():
    config = make_config([SLOT_A])
    start = datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)
    clock = FakeClock(start)
    authenticator = FakeAuthenticator(error=AuthenticationFailed("bad credentials"))
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[],
        authenticator=authenticator,
    )

    result = use_case.execute(skip_wait=True)

    assert result == 1
    assert booking_client.calls == []
    assert any("Login failed" in m for m in notifier.messages)
    assert not any("secret" in m for m in notifier.messages)


def test_skip_wait_outside_schedule_still_gets_a_full_retry_window():
    config = make_config([SLOT_A], retry_interval_seconds=1.0)
    start = datetime(2024, 1, 6, 16, 45, 0, tzinfo=TZ)  # hours after the configured window
    clock = FakeClock(start)
    use_case, booking_client, notifier, _ = build_use_case(
        config=config,
        clock=clock,
        outcomes=[BookingResult(BookingOutcome.NOT_OPEN_YET), BookingResult(BookingOutcome.BOOKED)],
    )

    result = use_case.execute(skip_wait=True)

    assert result == 0
    assert len(booking_client.calls) == 2
