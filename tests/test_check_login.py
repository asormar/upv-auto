from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier

from upv_auto.app.check_login import check_login
from upv_auto.domain.errors import AuthenticationBlocked, AuthenticationFailed
from upv_auto.domain.models import Credentials

CREDENTIALS = Credentials(username="user", password="super-secret")


def make_clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 19, 9, 50, tzinfo=ZoneInfo("Europe/Madrid")))


def test_check_login_success_notifies_ok():
    authenticator = FakeAuthenticator()
    verifier = FakeVerifier(valid=True)
    notifier = FakeNotifier()

    ok = check_login(CREDENTIALS, authenticator, verifier, notifier, make_clock())

    assert ok is True
    assert authenticator.calls == 1
    assert any("OK" in m for m in notifier.messages)


def test_check_login_authentication_failed_notifies_and_hides_password():
    authenticator = FakeAuthenticator(error=AuthenticationFailed("wrong username or password"))
    verifier = FakeVerifier(valid=True)
    notifier = FakeNotifier()

    ok = check_login(CREDENTIALS, authenticator, verifier, notifier, make_clock())

    assert ok is False
    assert any("Login failed" in m for m in notifier.messages)
    assert not any("super-secret" in m for m in notifier.messages)


def test_check_login_authentication_blocked_notifies():
    authenticator = FakeAuthenticator(error=AuthenticationBlocked("captcha detected"))
    verifier = FakeVerifier(valid=True)
    notifier = FakeNotifier()

    ok = check_login(CREDENTIALS, authenticator, verifier, notifier, make_clock())

    assert ok is False
    assert any("blocked" in m.lower() for m in notifier.messages)


def test_check_login_invalid_session_notifies():
    authenticator = FakeAuthenticator()
    verifier = FakeVerifier(valid=False)
    notifier = FakeNotifier()

    ok = check_login(CREDENTIALS, authenticator, verifier, notifier, make_clock())

    assert ok is False
    assert any("verification failed" in m.lower() for m in notifier.messages)
