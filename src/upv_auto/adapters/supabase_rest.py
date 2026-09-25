"""Supabase adapter: a thin httpx PostgREST client, using the service-role key.

Implements `UserDirectory` (see `ports.py`) against the schema in
`supabase/migrations/0001_multi_user.sql`: the batch roster, per-user
results, claiming a refresh job, and caching a fetched schedule. Every call
carries `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS entirely — only this
adapter, running on the GitHub Actions runner, is ever handed that key (see
design.md's Schema table).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from upv_auto.config import parse_booking_dict
from upv_auto.domain.errors import CredentialsUnavailable
from upv_auto.domain.models import GroupAvailability, RefreshJob, UserRecord

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class SupabaseRestUserDirectory:
    """`UserDirectory` backed by Supabase's auto-generated PostgREST API."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupabaseRestUserDirectory":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- UserDirectory ----------------------------------------------------

    def roster(self) -> list[UserRecord]:
        """Every user with a non-empty queue, via the `batch_roster()` RPC."""
        response = self._client.post("/rpc/batch_roster", json={})
        response.raise_for_status()
        return [
            UserRecord(
                user_id=row["user_id"],
                email=row["email"],
                sealed_credentials=row["sealed"],
                key_id=row["key_id"],
                bookings=[parse_booking_dict(b) for b in row["bookings"]],
            )
            for row in response.json()
        ]

    def record_result(self, user_id: str, run_id: str, status: str, summary: str) -> None:
        response = self._client.post(
            "/batch_results",
            json={"user_id": user_id, "run_id": run_id, "status": status, "summary": summary},
            headers={"Prefer": "return=minimal"},
        )
        response.raise_for_status()

    def claim_request(self, request_id: str) -> RefreshJob | None:
        """Load the job data for a request already claimed by the `refresh`
        Edge Function's `claim_refresh()` call — `refresh.yml` passes only
        `request_id`, so the runner looks up the rest here."""
        request_response = self._client.get(
            "/refresh_requests",
            params={"id": f"eq.{request_id}", "status": "eq.pending", "select": "id,user_id"},
        )
        request_response.raise_for_status()
        request_rows = request_response.json()
        if not request_rows:
            return None
        user_id = request_rows[0]["user_id"]

        cred_response = self._client.get(
            "/upv_credentials",
            params={"user_id": f"eq.{user_id}", "select": "sealed,key_id"},
        )
        cred_response.raise_for_status()
        cred_rows = cred_response.json()
        if not cred_rows:
            # Signed up but has not saved UPV credentials yet: raising here
            # (instead of returning None) lets the use case close the request
            # instead of leaving it `pending` until the 15-minute expiry,
            # which the web reads as a refresh that never ends.
            raise CredentialsUnavailable("This user has no stored UPV credentials")

        return RefreshJob(
            request_id=request_rows[0]["id"],
            user_id=user_id,
            sealed_credentials=cred_rows[0]["sealed"],
            key_id=cred_rows[0]["key_id"],
        )

    def save_schedule(self, user_id: str, groups: dict[str, GroupAvailability]) -> None:
        response = self._client.post(
            "/schedules",
            json={
                "user_id": user_id,
                "groups": {code: _serialize_group(group) for code, group in groups.items()},
                "fetched_at": _now_iso(),
            },
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()

    # -- extra: not part of `UserDirectory`, used only by `book-all` ------

    def upsert_settings(self, settings: dict) -> None:
        """Sync the one global `app_settings` row from `config.yaml`.

        Not part of the `UserDirectory` protocol (`run_batch` never calls
        it) — the `book-all` command calls it directly once per run, so the
        web frontend's `getConfig()` (activity/window/limits) reflects
        whatever `config.yaml` currently says.
        """
        response = self._client.post(
            "/app_settings",
            json={"id": 1, "settings": settings},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()

    def finish_request(self, request_id: str, ok: bool, error_code: str | None) -> None:
        response = self._client.patch(
            "/refresh_requests",
            params={"id": f"eq.{request_id}"},
            json={
                "status": "done" if ok else "failed",
                "error_code": error_code,
                "finished_at": _now_iso(),
            },
            headers={"Prefer": "return=minimal"},
        )
        response.raise_for_status()


def _serialize_group(group: GroupAvailability) -> dict:
    """The raw shape cached in `schedules.groups`: no `booking_path` (design.md's
    "Schedule cache" decision — the client derives booking state from the live queue,
    which is edited independently of the cached schedule)."""
    return {
        "code": group.code,
        "state": group.state.name,
        "free_places": group.free_places,
        "day": group.day,
        "time": group.time,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
