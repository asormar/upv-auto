"""Ports: the interfaces the application core depends on.

Adapters implement these Protocols; the application layer (app/) only ever
talks to these shapes, never to a concrete adapter class.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from upv_auto.domain.models import BookingResult, Credentials, Session, Slot


class Authenticator(Protocol):
    def login(self, credentials: Credentials) -> Session: ...


class SessionVerifier(Protocol):
    def is_valid(self, session: Session) -> bool: ...


class BookingClient(Protocol):
    def book(self, session: Session, slot: Slot) -> BookingResult: ...


class Notifier(Protocol):
    def notify(self, text: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...
