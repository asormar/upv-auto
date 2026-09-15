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
    """A candidate booking slot, described in configuration terms."""

    facility: str
    sport: str
    day_offset_days: int
    start_time: str  # "HH:MM"

    @property
    def label(self) -> str:
        return f"{self.facility}/{self.sport} @ +{self.day_offset_days}d {self.start_time}"


@dataclass(frozen=True)
class Session:
    """An authenticated browsing session exported from Playwright."""

    cookies: list[dict[str, Any]]
    user_agent: str


class BookingOutcome(Enum):
    BOOKED = auto()
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
