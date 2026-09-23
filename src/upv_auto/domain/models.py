"""Domain models: plain data structures with no I/O dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any


@dataclass(frozen=True)
class Credentials:
    """UPV CAS credentials. repr/str never reveal the password."""

    username: str
    password: str

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Credentials(username={self.username!r}, password='***')"


@dataclass(frozen=True)
class Slot:
    """A candidate booking slot: a UPV activity group code, e.g. 'MUS074'."""

    group_code: str

    @property
    def label(self) -> str:
        return self.group_code


@dataclass(frozen=True)
class BookingTarget:
    """One place to secure: the preferred group first, then alternatives if it is full."""

    options: tuple[Slot, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("A booking target needs at least one group")

    @property
    def label(self) -> str:
        preferred, *alternatives = (slot.label for slot in self.options)
        return f"{preferred} (alternatives: {', '.join(alternatives)})" if alternatives else preferred


@dataclass(frozen=True)
class Activity:
    """The UPV sports activity (campus + programme + activity) whose groups are booked."""

    campus: str
    tipoact: str
    codacti: str
    name: str = ""


class GroupState(Enum):
    """The state of one activity group cell, as scraped from the activity table."""

    BOOKABLE = auto()
    FULL = auto()
    ENROLLED = auto()
    UNAVAILABLE = auto()


@dataclass(frozen=True)
class GroupAvailability:
    """One parsed group cell from the UPV activity table.

    `day` and `time` come from the cell's position in the weekly table (its
    column header and its row label). They are absent when the page does not
    lay the group out in that grid.
    """

    code: str
    state: GroupState
    free_places: int | None = None
    booking_path: str | None = None
    day: str | None = None
    time: str | None = None


@dataclass(frozen=True)
class Session:
    """An authenticated browsing session exported from Playwright."""

    cookies: list[dict[str, Any]]
    user_agent: str


class BookingOutcome(Enum):
    """Why an activity-table read could not be turned into a `TableSnapshot`."""

    SESSION_EXPIRED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class TableSnapshot:
    """Result of reading the activity table: parsed groups, or why it could not be read."""

    groups: dict[str, GroupAvailability] | None = None
    failure: BookingOutcome | None = None  # only SESSION_EXPIRED or ERROR
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.groups is not None


@dataclass(frozen=True)
class BookingWindow:
    opens_at: datetime
    closes_at: datetime
    retry_interval_seconds: float


@dataclass(frozen=True)
class UserRecord:
    """One roster entry for the multi-user batch: a user with a non-empty queue.

    `sealed_credentials`/`key_id` are opened via `CredentialOpener` just
    before that user's turn, never eagerly for the whole roster at once.
    """

    user_id: str
    email: str
    sealed_credentials: str
    key_id: str
    bookings: list[BookingTarget]


@dataclass(frozen=True)
class RefreshJob:
    """A claimed schedule-refresh request: enough to unseal and fetch one user's schedule."""

    request_id: str
    user_id: str
    sealed_credentials: str
    key_id: str
