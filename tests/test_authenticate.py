from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier

from upv_auto.app.authenticate import authenticate
from upv_auto.domain.errors import (
    AuthenticationBlocked,
    AuthenticationFailed,
    AuthenticationUnavailable,
)
from upv_auto.domain.models import Credentials

CREDENTIALS = Credentials(username="user", password="super-secret")


def make_clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 19, 9, 50, tzinfo=ZoneInfo("Europe/Madrid")))


def test_retries_when_upv_is_unavailable_then_succeeds():
    authenticator = FakeAuthenticator(
        errors=[AuthenticationUnavailable("HTTP 503"), AuthenticationUnavailable("HTTP 503")]
    )
    clock = make_clock()
    notifier = FakeNotifier()

    session = authenticate(
        CREDENTIALS, authenticator, FakeVerifier(), notifier, clock, retry_delay_seconds=10
    )

    assert session is not None
    assert authenticator.calls == 3
    assert clock.sleep_calls == [10, 10]
    assert notifier.messages == []


def test_gives_up_after_max_attempts_and_notifies_last_problem():
    authenticator = FakeAuthenticator(error=AuthenticationUnavailable("HTTP 503"))
    clock = make_clock()
    notifier = FakeNotifier()

    session = authenticate(
        CREDENTIALS, authenticator, FakeVerifier(), notifier, clock, max_attempts=3
    )

    assert session is None
    assert authenticator.calls == 3
    assert len(clock.sleep_calls) == 2  # no sleep after the final attempt
    assert "after 3 attempt(s)" in notifier.messages[0]
    assert "HTTP 503" in notifier.messages[0]


def test_invalid_session_is_retried():
    verifier = FakeVerifier(valid=False)
    authenticator = FakeAuthenticator()

    session = authenticate(
        CREDENTIALS, authenticator, verifier, FakeNotifier(), make_clock(), max_attempts=2
    )

    assert session is None
    assert authenticator.calls == 2


def test_rejected_credentials_are_never_retried():
    authenticator = FakeAuthenticator(error=AuthenticationFailed("wrong password"))
    clock = make_clock()

    session = authenticate(CREDENTIALS, authenticator, FakeVerifier(), FakeNotifier(), clock)

    assert session is None
    assert authenticator.calls == 1
    assert clock.sleep_calls == []


def test_blocked_login_is_never_retried():
    authenticator = FakeAuthenticator(error=AuthenticationBlocked("captcha"))

    session = authenticate(
        CREDENTIALS, authenticator, FakeVerifier(), FakeNotifier(), make_clock()
    )

    assert session is None
    assert authenticator.calls == 1
