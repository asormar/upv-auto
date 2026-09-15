"""In-memory fakes used across tests. No network, no real browser, no real clock."""

from __future__ import annotations

from datetime import datetime, timedelta

from upv_auto.domain.models import BookingOutcome, GroupAvailability, GroupState, Session, TableSnapshot

_STATE_BY_NAME = {state.name: state for state in GroupState}


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
    """Returns a fresh Session on each call, or raises a configured error.

    `error` is raised on every call; `errors` are raised one per call, in order,
    after which logins succeed.
    """

    def __init__(self, error: Exception | None = None, errors: list[Exception] | None = None) -> None:
        self._error = error
        self._errors = list(errors or [])
        self.calls = 0

    def login(self, credentials) -> Session:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._errors:
            raise self._errors.pop(0)
        return Session(cookies=[], user_agent=f"fake-agent-{self.calls}")


class FakeVerifier:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    def is_valid(self, session: Session) -> bool:
        return self.valid


def table(**states: str) -> TableSnapshot:
    """Build a TableSnapshot from `code=state_name` kwargs, e.g. `table(MUS074="BOOKABLE")`.

    A BOOKABLE group is given a `booking_path` of `book/<code>` so
    `follow_booking` can be exercised without repeating it by hand.
    """
    groups = {}
    for code, state_name in states.items():
        state = _STATE_BY_NAME[state_name]
        groups[code] = GroupAvailability(
            code=code,
            state=state,
            booking_path=f"book/{code}" if state is GroupState.BOOKABLE else None,
        )
    return TableSnapshot(groups=groups)


def expired() -> TableSnapshot:
    return TableSnapshot(failure=BookingOutcome.SESSION_EXPIRED)


def error(message: str = "boom") -> TableSnapshot:
    return TableSnapshot(failure=BookingOutcome.ERROR, message=message)


class FakeActivityTableClient:
    """Replays scripted `TableSnapshot`s: a queue for `fetch_groups`, a per-code queue for `follow_booking`."""

    def __init__(
        self,
        fetch_results: list[TableSnapshot],
        follow_results: dict[str, list[TableSnapshot]] | None = None,
    ) -> None:
        self._fetch_results = list(fetch_results)
        self._follow_results = {code: list(items) for code, items in (follow_results or {}).items()}
        self.calls: list[tuple] = []

    def fetch_groups(self, session) -> TableSnapshot:
        self.calls.append(("fetch",))
        return self._fetch_results.pop(0)

    def follow_booking(self, session, group: GroupAvailability) -> TableSnapshot:
        self.calls.append(("follow", group.code))
        return self._follow_results[group.code].pop(0)


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, text: str) -> None:
        self.messages.append(text)
