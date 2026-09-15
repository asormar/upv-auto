"""In-memory fakes used across tests. No network, no real browser, no real clock."""

from __future__ import annotations

from datetime import datetime, timedelta

from upv_auto.domain.models import Session


class FakeClock:
    """A clock whose `sleep` advances virtual time instantly."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += timedelta(seconds=seconds)


class FakeAuthenticator:
    """Returns a fresh Session on each call, or raises a configured error."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.calls = 0

    def login(self, credentials) -> Session:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return Session(cookies=[], user_agent=f"fake-agent-{self.calls}")


class FakeVerifier:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    def is_valid(self, session: Session) -> bool:
        return self.valid


class FakeBookingClient:
    """Replays a fixed sequence of outcomes (or exceptions), one per `book()` call."""

    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple] = []

    def book(self, session, slot):
        self.calls.append((session, slot))
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, text: str) -> None:
        self.messages.append(text)
