"""Tests for `refresh --request-id` (schedule-refresh spec) and the
`app.refresh_user` use case it calls.

The CLI test is the threat-matrix RED test task 4.1 asks for: a non-UUID
`--request-id` must be rejected before it reaches Supabase, GitHub, or the
UPV login flow (threat matrix: workflow-input injection — `request_id` is a
GitHub Actions `workflow_dispatch` input, so the CLI must never trust it).
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo

from fakes import FakeActivityTableClient, FakeAuthenticator, FakeClock, FakeNotifier, FakeVerifier, error, table

from upv_auto.__main__ import main
from upv_auto.app.refresh_user import refresh_user
from upv_auto.config import AppConfig, UpvConfig, WindowConfig
from upv_auto.domain.errors import CredentialsUnavailable
from upv_auto.domain.models import Activity, Credentials, RefreshJob

TZ = ZoneInfo("Europe/Madrid")
REQUEST_ID = "5c1f6f0a-2b3c-4d5e-8f9a-1234567890ab"


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
    """In-memory `UserDirectory`: only the methods `refresh_user` calls are wired."""

    def __init__(self, job: RefreshJob | None) -> None:
        self._job = job
        self.saved: list[tuple[str, dict]] = []
        self.finished: list[tuple[str, bool, str | None]] = []

    def roster(self):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def record_result(self, user_id, run_id, status, summary):  # pragma: no cover
        raise NotImplementedError

    def claim_request(self, request_id: str) -> RefreshJob | None:
        return self._job

    def save_schedule(self, user_id: str, groups) -> None:
        self.saved.append((user_id, groups))

    def finish_request(self, request_id: str, ok: bool, error_code: str | None) -> None:
        self.finished.append((request_id, ok, error_code))


class FailingOpener:
    def open(self, sealed: str, key_id: str) -> Credentials:
        raise CredentialsUnavailable("unknown key")


class WorkingOpener:
    def open(self, sealed: str, key_id: str) -> Credentials:
        return Credentials(username=f"user-{sealed}", password="pw")


def make_job() -> RefreshJob:
    return RefreshJob(request_id=REQUEST_ID, user_id="u-1", sealed_credentials="sealed", key_id="k1")


# -- CLI: threat-matrix RED test (task 4.1) -------------------------------


def test_cli_rejects_a_non_uuid_request_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no config.yaml here: proves we never get that far
    exit_code = main(["refresh", "--request-id", "'; DROP TABLE refresh_requests; --"])
    assert exit_code == 1


def test_cli_rejects_an_empty_request_id():
    assert main(["refresh", "--request-id", ""]) == 1


# -- app.refresh_user: state transitions -----------------------------------


def test_claim_miss_returns_error_without_touching_credentials():
    directory = FakeUserDirectory(job=None)

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        WorkingOpener(),
        FakeAuthenticator(),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[]),
    )

    assert result == 1
    assert directory.finished == []  # nothing to finish: the request was never claimed
    assert directory.saved == []


def test_credentials_unavailable_finishes_the_request_as_failed():
    directory = FakeUserDirectory(job=make_job())

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        FailingOpener(),
        FakeAuthenticator(),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[]),
    )

    assert result == 1
    assert directory.finished == [(REQUEST_ID, False, "credentials_unavailable")]
    assert directory.saved == []


def test_fetch_failure_finishes_the_request_as_failed():
    directory = FakeUserDirectory(job=make_job())

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        WorkingOpener(),
        FakeAuthenticator(),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[error("boom")]),
    )

    assert result == 1
    assert directory.finished == [(REQUEST_ID, False, "fetch_failed")]
    assert directory.saved == []


def test_successful_refresh_saves_the_schedule_and_finishes_ok():
    directory = FakeUserDirectory(job=make_job())
    opened: list[Credentials] = []

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        WorkingOpener(),
        FakeAuthenticator(),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[table(MUS074="BOOKABLE")]),
        on_credentials_opened=opened.append,
    )

    assert result == 0
    assert directory.finished == [(REQUEST_ID, True, None)]
    [(user_id, groups)] = directory.saved
    assert user_id == "u-1"
    assert "MUS074" in groups
    assert len(opened) == 1  # credentials were reported for log-hygiene registration


def test_login_failure_finishes_the_request_as_failed():
    directory = FakeUserDirectory(job=make_job())
    from upv_auto.domain.errors import AuthenticationFailed

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        WorkingOpener(),
        FakeAuthenticator(error=AuthenticationFailed("bad credentials")),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[]),
    )

    assert result == 1
    assert directory.finished == [(REQUEST_ID, False, "fetch_failed")]


class NoCredentialsDirectory(FakeUserDirectory):
    """A user who signed up but never saved UPV credentials: the adapter
    raises instead of returning a job (`SupabaseRestUserDirectory`)."""

    def claim_request(self, request_id: str) -> RefreshJob:
        raise CredentialsUnavailable("no stored credentials")


def test_missing_stored_credentials_finishes_the_request():
    # Otherwise the row stays `pending` for the full 15-minute expiry and the
    # web shows a refresh that never ends.
    directory = NoCredentialsDirectory(job=None)

    result = refresh_user(
        REQUEST_ID,
        base_config(),
        directory,
        WorkingOpener(),
        FakeAuthenticator(),
        FakeVerifier(valid=True),
        FakeNotifier(),
        FakeClock(datetime(2024, 1, 6, 9, 0, 0, tzinfo=TZ)),
        FakeActivityTableClient(fetch_results=[]),
    )

    assert result == 1
    assert directory.finished == [(REQUEST_ID, False, "credentials_unavailable")]
