"""Ports: the interfaces the application core depends on.

Adapters implement these Protocols; the application layer (app/) only ever
talks to these shapes, never to a concrete adapter class.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from upv_auto.domain.models import (
    Credentials,
    GroupAvailability,
    RefreshJob,
    Session,
    TableSnapshot,
    UserRecord,
)


class Authenticator(Protocol):
    def login(self, credentials: Credentials) -> Session: ...


class SessionVerifier(Protocol):
    def is_valid(self, session: Session) -> bool: ...


class ActivityTableClient(Protocol):
    def fetch_groups(self, session: Session) -> TableSnapshot: ...

    def follow_booking(self, session: Session, group: GroupAvailability) -> TableSnapshot: ...


class Notifier(Protocol):
    def notify(self, text: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class UserDirectory(Protocol):
    """Multi-user persistence: the Supabase-backed roster, results, and refresh jobs.

    Implemented by `adapters.supabase_rest`, with the service-role key.
    """

    def roster(self) -> list[UserRecord]:
        """Every user with a non-empty booking queue, for this week's batch."""
        ...

    def record_result(self, user_id: str, run_id: str, status: str, summary: str) -> None:
        """Record one user's outcome for this batch run."""
        ...

    def claim_request(self, request_id: str) -> RefreshJob | None:
        """Load the job data for an already-claimed schedule-refresh request."""
        ...

    def save_schedule(self, user_id: str, groups: dict[str, GroupAvailability]) -> None:
        """Cache a user's freshly fetched activity groups."""
        ...

    def finish_request(self, request_id: str, ok: bool, error_code: str | None) -> None:
        """Mark a refresh request `done` or `failed`."""
        ...


class CredentialOpener(Protocol):
    """Unseals credentials sealed in the browser (see `web/src/seal.ts`)."""

    def open(self, sealed: str, key_id: str) -> Credentials:
        """Return the unsealed credentials, or raise `CredentialsUnavailable`."""
        ...
