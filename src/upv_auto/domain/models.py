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
    """One parsed group cell from the UPV activity table."""

    code: str
    state: GroupState
    free_places: int | None = None
    booking_path: str | None = None


@dataclass(frozen=True)
class Session:
    """An authenticated browsing session exported from Playwright."""

    cookies: list[dict[str, Any]]
    user_agent: str


class BookingOutcome(Enum):
    BOOKED = auto()
    # Enrolled before we acted: may be the previous week's table, so not a success.
    ALREADY_ENROLLED = auto()
    NOT_OPEN_YET = auto()
    TAKEN = auto()
    SESSION_EXPIRED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class BookingResult:
    outcome: BookingOutcome
    message: str = ""


@dataclass(frozen=True)
class BookingWindow:
    opens_at: datetime
    closes_at: datetime
    retry_interval_seconds: float
