from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeActivityTableClient, FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier, error, expired, table

from upv_auto.app.list_groups import list_groups
from upv_auto.config import AppConfig, UpvConfig, WindowConfig
from upv_auto.domain.errors import AuthenticationFailed
from upv_auto.domain.models import Activity, BookingTarget, Credentials, Slot

TZ = ZoneInfo("Europe/Madrid")


def make_config() -> AppConfig:
    return AppConfig(
        timezone="Europe/Madrid",
        upv=UpvConfig(entry_url="https://example.test/entry", session_check_url="https://example.test/entry"),
        window=WindowConfig(weekday="saturday", opens_at="10:00:00", closes_at="10:03:00", retry_interval_seconds=1.5),
        activity=Activity(campus="V", tipoact="6894", codacti="21948", name="MUSCULACION"),
        bookings=[BookingTarget((Slot(group_code="MUS074"),))],
        credentials=Credentials(username="user", password="secret"),
        email=None,
    )


def make_clock() -> FakeClock:
    return FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ))


def test_list_groups_prints_every_group_sorted_by_code(capsys):
    config = make_config()
    table_client = FakeActivityTableClient(fetch_results=[table(MUS075="BOOKABLE", MUS074="FULL")])

    ok = list_groups(config, FakeAuthenticator(), FakeVerifier(valid=True), FakeNotifier(), make_clock(), table_client)

    assert ok is True
    out = capsys.readouterr().out
    assert out.index("MUS074") < out.index("MUS075")
    assert "MUS074: FULL" in out
    assert "MUS075: BOOKABLE" in out


def test_list_groups_login_failure_does_not_fetch_the_table():
    config = make_config()
    table_client = FakeActivityTableClient(fetch_results=[])
    authenticator = FakeAuthenticator(error=AuthenticationFailed("bad credentials"))
    notifier = FakeNotifier()

    ok = list_groups(config, authenticator, FakeVerifier(valid=True), notifier, make_clock(), table_client)

    assert ok is False
    assert table_client.calls == []
    assert any("Login failed" in m for m in notifier.messages)


def test_list_groups_session_expired_notifies_and_fails():
    config = make_config()
    table_client = FakeActivityTableClient(fetch_results=[expired()])
    notifier = FakeNotifier()

    ok = list_groups(config, FakeAuthenticator(), FakeVerifier(valid=True), notifier, make_clock(), table_client)

    assert ok is False
    assert any("expired" in m.lower() for m in notifier.messages)


def test_list_groups_fetch_error_notifies_and_fails():
    config = make_config()
    table_client = FakeActivityTableClient(fetch_results=[error("boom")])
    notifier = FakeNotifier()

    ok = list_groups(config, FakeAuthenticator(), FakeVerifier(valid=True), notifier, make_clock(), table_client)

    assert ok is False
    assert any("Failed to fetch activity table" in m for m in notifier.messages)
