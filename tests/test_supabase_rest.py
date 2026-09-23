"""Focused tests for `adapters.supabase_rest.SupabaseRestUserDirectory`.

Each test asserts the exact PostgREST request shape (method, path, params or
body) rather than hitting a real Supabase project — this is a REST client,
not the SQL layer itself (that is the manual `supabase start` checklist).
"""

from __future__ import annotations

import json

import httpx
import pytest

from upv_auto.adapters.supabase_rest import SupabaseRestUserDirectory
from upv_auto.domain.models import GroupAvailability, GroupState

BASE_URL = "https://example.supabase.co"
SERVICE_KEY = "service-role-test-key"


def make_directory(handler) -> SupabaseRestUserDirectory:
    transport = httpx.MockTransport(handler)
    return SupabaseRestUserDirectory(BASE_URL, SERVICE_KEY, transport=transport)


def test_roster_calls_batch_roster_rpc_and_parses_bookings():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/batch_roster"
        assert request.headers["apikey"] == SERVICE_KEY
        assert request.headers["Authorization"] == f"Bearer {SERVICE_KEY}"
        return httpx.Response(
            200,
            json=[
                {
                    "user_id": "u-1",
                    "email": "alice@example.test",
                    "sealed": "sealed-ciphertext",
                    "key_id": "v1",
                    "bookings": [{"group_code": "MUS021", "alternatives": ["MUS036"]}],
                }
            ],
        )

    with make_directory(handler) as directory:
        roster = directory.roster()

    assert len(roster) == 1
    user = roster[0]
    assert user.user_id == "u-1"
    assert user.email == "alice@example.test"
    assert user.sealed_credentials == "sealed-ciphertext"
    assert user.key_id == "v1"
    assert len(user.bookings) == 1
    assert [slot.group_code for slot in user.bookings[0].options] == ["MUS021", "MUS036"]


def test_record_result_posts_a_batch_results_row():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/batch_results"
        assert request.headers["Prefer"] == "return=minimal"
        body = json.loads(request.content)
        assert body == {"user_id": "u-1", "run_id": "run-42", "status": "booked", "summary": "Booked MUS021"}
        return httpx.Response(201)

    with make_directory(handler) as directory:
        directory.record_result("u-1", "run-42", "booked", "Booked MUS021")


def test_claim_request_joins_refresh_request_with_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/v1/refresh_requests":
            assert request.method == "GET"
            assert request.url.params["id"] == "eq.req-1"
            assert request.url.params["status"] == "eq.pending"
            return httpx.Response(200, json=[{"id": "req-1", "user_id": "u-1"}])
        assert request.url.path == "/rest/v1/upv_credentials"
        assert request.url.params["user_id"] == "eq.u-1"
        return httpx.Response(200, json=[{"sealed": "sealed-ciphertext", "key_id": "v1"}])

    with make_directory(handler) as directory:
        job = directory.claim_request("req-1")

    assert job is not None
    assert job.request_id == "req-1"
    assert job.user_id == "u-1"
    assert job.sealed_credentials == "sealed-ciphertext"
    assert job.key_id == "v1"


def test_claim_request_returns_none_when_the_request_is_not_pending():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])  # no pending row with this id

    with make_directory(handler) as directory:
        job = directory.claim_request("req-missing")

    assert job is None


def test_save_schedule_upserts_raw_groups_without_booking_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/schedules"
        assert request.headers["Prefer"] == "resolution=merge-duplicates,return=minimal"
        body = json.loads(request.content)
        assert body["user_id"] == "u-1"
        assert body["groups"] == {
            "MUS021": {"code": "MUS021", "state": "BOOKABLE", "free_places": 5, "day": "Lunes", "time": "10:00"}
        }
        assert "fetched_at" in body
        return httpx.Response(201)

    groups = {
        "MUS021": GroupAvailability(
            code="MUS021",
            state=GroupState.BOOKABLE,
            free_places=5,
            booking_path="book/MUS021",  # must NOT be serialized (design.md: no booking_path in cache)
            day="Lunes",
            time="10:00",
        )
    }

    with make_directory(handler) as directory:
        directory.save_schedule("u-1", groups)


def test_finish_request_patches_status_and_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/rest/v1/refresh_requests"
        assert request.url.params["id"] == "eq.req-1"
        body = json.loads(request.content)
        assert body["status"] == "failed"
        assert body["error_code"] == "upv_unavailable"
        assert "finished_at" in body
        return httpx.Response(204)

    with make_directory(handler) as directory:
        directory.finish_request("req-1", False, "upv_unavailable")


def test_upsert_settings_posts_the_global_row():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/app_settings"
        assert request.headers["Prefer"] == "resolution=merge-duplicates,return=minimal"
        body = json.loads(request.content)
        assert body == {"id": 1, "settings": {"timezone": "Europe/Madrid"}}
        return httpx.Response(201)

    with make_directory(handler) as directory:
        directory.upsert_settings({"timezone": "Europe/Madrid"})


def test_raises_on_an_http_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    with make_directory(handler) as directory:
        with pytest.raises(httpx.HTTPStatusError):
            directory.roster()
