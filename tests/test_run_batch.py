"""Tests for `app.run_batch` (weekly-batch-booking spec: "Per-User Failure
Isolation", "Per-User Result Recording", "Per-User Email Notification";
booking-queue spec: "Empty Queue Is Valid").
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeActivityTableClient, FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier, table

from upv_auto.app.run_batch import run_batch
from upv_auto.config import AppConfig, UpvConfig, WindowConfig
from upv_auto.domain.errors import AuthenticationFailed
from upv_auto.domain.models import Activity, BookingTarget, Credentials, Slot, UserRecord

TZ = ZoneInfo("Europe/Madrid")
RUN_ID = "run-123"
SLOT = Slot(group_code="MUS074")


def base_config() -> AppConfig:
    return AppConfig(
        timezone="Europe/Madrid",
        upv=UpvConfig(entry_url="https://example.test/entry", session_check_url="https://example.test/entry"),
        window=WindowConfig(
            weekday="saturday", opens_at="10:00:00", closes_at="10:03:00", retry_interval_seconds=0.01
        ),
        activity=Activity(campus="V", tipoact="6894", codacti="21948", name="MUSCULACION"),
        bookings=[],
        credentials=Credentials(username="placeholder", password="placeholder"),
        email=None,
    )


class FakeUserDirectory:
    """In-memory `UserDirectory`: records every `record_result` call for assertions."""

    def __init__(self, roster: list[UserRecord]) -> None:
        self._roster = roster
        self.results: list[tuple[str, str, str, str]] = []

    def roster(self) -> list[UserRecord]:
        return list(self._roster)

    def record_result(self, user_id: str, run_id: str, status: str, summary: str) -> None:
        self.results.append((user_id, run_id, status, summary))

    def claim_request(self, request_id: str):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def save_schedule(self, user_id: str, groups) -> None:  # pragma: no cover
        raise NotImplementedError

    def finish_request(self, request_id: str, ok: bool, error_code: str | None) -> None:  # pragma: no cover
        raise NotImplementedError


class FakeCredentialOpener:
    """Deterministically "unseals" a test sealed value into a matching username."""

    def open(self, sealed: str, key_id: str) -> Credentials:
        return Credentials(username=f"user-{sealed}", password="pw")


def make_user(user_id: str, sealed: str) -> UserRecord:
    return UserRecord(
        user_id=user_id,
        email=f"{user_id}@example.test",
        sealed_credentials=sealed,
        key_id="k1",
        bookings=[BookingTarget((SLOT,))],
    )


def make_factories(*, failing_username: str | None = None):
    """Build authenticator/verifier/table_client factories.

    `failing_username` (if set) makes that one user's login raise
    `AuthenticationFailed`; every other user logs in and books successfully.
    """

    def authenticator_factory(config: AppConfig) -> FakeAuthenticator:
        if config.credentials.username == failing_username:
            return FakeAuthenticator(error=AuthenticationFailed("bad credentials"))
        return FakeAuthenticator()

    def verifier_factory(config: AppConfig) -> FakeVerifier:
        return FakeVerifier(valid=True)

    def table_client_factory(config: AppConfig):
        client = FakeActivityTableClient(
            fetch_results=[table(MUS074="BOOKABLE")],
            follow_results={"MUS074": [table(MUS074="ENROLLED")]},
        )
        return nullcontext(client)

    return authenticator_factory, verifier_factory, table_client_factory


def test_one_users_login_failure_does_not_block_the_others():
    """weekly-batch-booking: "A failure while processing one user's booking
    ... MUST NOT abort or skip processing for any other user in the batch."
    """
    users = [make_user("u-a", "a"), make_user("u-b", "b"), make_user("u-c", "c")]
    directory = FakeUserDirectory(users)
    authenticator_factory, verifier_factory, table_client_factory = make_factories(
        failing_username="user-b"
    )
    sent: dict[str, FakeNotifier] = {}

    def notifier_factory(user: UserRecord) -> FakeNotifier:
        notifier = FakeNotifier()
        sent[user.user_id] = notifier
        return notifier

    result = run_batch(
        base_config(),
        directory,
        FakeCredentialOpener(),
        authenticator_factory,
        verifier_factory,
        table_client_factory,
        notifier_factory,
        FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)),
        RUN_ID,
        skip_wait=True,
    )

    assert result == 1  # not everyone succeeded
    statuses = {user_id: status for user_id, _, status, _ in directory.results}
    assert statuses == {"u-a": "booked", "u-b": "incomplete", "u-c": "booked"}
    # Every user was still recorded and still emailed — B's failure was isolated.
    assert set(sent.keys()) == {"u-a", "u-b", "u-c"}
    assert sent["u-b"].messages  # got a message describing its own failure
    assert sent["u-a"].messages and sent["u-c"].messages  # A and C got their own outcome too


def test_all_users_succeed_returns_zero():
    users = [make_user("u-a", "a"), make_user("u-b", "b")]
    directory = FakeUserDirectory(users)
    authenticator_factory, verifier_factory, table_client_factory = make_factories()

    result = run_batch(
        base_config(),
        directory,
        FakeCredentialOpener(),
        authenticator_factory,
        verifier_factory,
        table_client_factory,
        lambda user: FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)),
        RUN_ID,
        skip_wait=True,
    )

    assert result == 0
    assert {user_id for user_id, *_ in directory.results} == {"u-a", "u-b"}
    assert all(status == "booked" for *_, status, _ in directory.results)


def test_empty_roster_produces_no_result_and_no_email():
    """booking-queue: "Empty Queue Is Valid" — a roster with nobody in it (every
    queue was empty) makes no booking attempt, no result row, and no email."""
    directory = FakeUserDirectory([])  # matches `batch_roster()` excluding empty queues
    notifier_calls: list[UserRecord] = []

    def notifier_factory(user: UserRecord) -> FakeNotifier:
        notifier_calls.append(user)
        return FakeNotifier()

    result = run_batch(
        base_config(),
        directory,
        FakeCredentialOpener(),
        *make_factories(),
        notifier_factory,
        FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)),
        RUN_ID,
        skip_wait=True,
    )

    assert result == 0
    assert directory.results == []
    assert notifier_calls == []


def test_credentials_unavailable_is_isolated_and_recorded():
    class FailingOpener:
        def open(self, sealed: str, key_id: str) -> Credentials:
            from upv_auto.domain.errors import CredentialsUnavailable

            if sealed == "bad":
                raise CredentialsUnavailable("unknown key")
            return Credentials(username=f"user-{sealed}", password="pw")

    users = [make_user("u-good", "good"), make_user("u-bad", "bad")]
    directory = FakeUserDirectory(users)
    authenticator_factory, verifier_factory, table_client_factory = make_factories()

    result = run_batch(
        base_config(),
        directory,
        FailingOpener(),
        authenticator_factory,
        verifier_factory,
        table_client_factory,
        lambda user: FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 10, 0, 0, tzinfo=TZ)),
        RUN_ID,
        skip_wait=True,
    )

    assert result == 1
    statuses = {user_id: status for user_id, _, status, _ in directory.results}
    assert statuses == {"u-good": "booked", "u-bad": "credentials_unavailable"}
