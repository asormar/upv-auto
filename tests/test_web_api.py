from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from upv_auto.adapters.web.api import ScheduleStore, create_app
from upv_auto.config import load_config
from upv_auto.domain.models import GroupAvailability, GroupState

CONFIG = """timezone: Europe/Madrid

upv:
  entry_url: https://example.test/entry
  session_check_url: https://example.test/check

window:
  weekday: saturday
  opens_at: '10:01:00'
  closes_at: '10:04:00'
  retry_interval_seconds: 1.5

activity:
  name: MUSCULACION
  campus: V
  tipoact: '6894'
  codacti: '21948'

# Keep me
bookings:
  - group_code: MUS021
  - group_code: MUS022
    alternatives: [MUS037]
"""

GROUPS = {
    "MUS021": GroupAvailability("MUS021", GroupState.ENROLLED, day="Martes", time="12:30-13:30"),
    "MUS022": GroupAvailability("MUS022", GroupState.FULL, day="Martes", time="13:30-14:30"),
    "MUS037": GroupAvailability(
        "MUS037", GroupState.BOOKABLE, free_places=4, booking_path="x", day="Miércoles",
        time="13:30-14:30",
    ),
    "MUS001": GroupAvailability("MUS001", GroupState.FULL, day="Lunes", time="07:35-08:30"),
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    calls = []

    def fake_fetch(config):
        calls.append(config.activity.name)
        return GROUPS

    app = create_app(config_path=config_path, store=ScheduleStore(fake_fetch))
    test_client = TestClient(app)
    test_client.config_path = config_path
    test_client.fetch_calls = calls
    return test_client


def test_config_endpoint_exposes_bookings_and_limits(client):
    body = client.get("/api/config").json()

    assert body["activity"]["name"] == "MUSCULACION"
    assert body["limits"] == {"max_sessions": 10, "max_per_activity": 6}
    assert body["bookings"] == [
        {"group_code": "MUS021", "alternatives": []},
        {"group_code": "MUS022", "alternatives": ["MUS037"]},
    ]


def test_schedule_groups_slots_by_day_in_week_order(client):
    body = client.get("/api/schedule").json()

    assert [day["name"] for day in body["days"]] == ["Lunes", "Martes", "Miércoles"]
    martes = body["days"][1]["slots"]
    assert [slot["code"] for slot in martes] == ["MUS021", "MUS022"]
    assert martes[0]["queued"] is True and martes[0]["priority"] == 1
    assert body["days"][2]["slots"][0]["is_alternative"] is True


def test_the_limit_counts_saturdays_queue_not_this_weeks_enrolments(client):
    body = client.get("/api/schedule").json()

    # Two bookings queued; MUS021 is also enrolled *this* week, which must not
    # inflate what Saturday would book.
    assert body["limits"]["queued"] == 2
    assert body["limits"]["enrolled_this_week"] == 1
    assert body["limits"]["max_per_activity"] == 6


def test_queueing_a_group_you_are_already_enrolled_in_counts_once(client):
    client.put("/api/bookings", json={"bookings": [{"group_code": "MUS021"}]})

    limits = client.get("/api/schedule").json()["limits"]

    assert limits["queued"] == 1
    assert limits["enrolled_this_week"] == 1


def test_schedule_is_cached_until_refresh_is_asked_for(client):
    client.get("/api/schedule")
    client.get("/api/schedule")
    assert len(client.fetch_calls) == 1

    client.get("/api/schedule", params={"refresh": "true"})
    assert len(client.fetch_calls) == 2


def test_saving_bookings_rewrites_the_config_and_keeps_comments(client):
    response = client.put(
        "/api/bookings",
        json={"bookings": [{"group_code": "MUS037", "alternatives": ["MUS001"]}]},
    )

    assert response.status_code == 200
    assert response.json()["bookings"] == [
        {"group_code": "MUS037", "alternatives": ["MUS001"]}
    ]
    text = client.config_path.read_text(encoding="utf-8")
    assert "# Keep me" in text
    assert load_config(client.config_path).bookings[0].options[0].group_code == "MUS037"


def test_saving_rejects_an_invalid_code(client):
    response = client.put("/api/bookings", json={"bookings": [{"group_code": "nope"}]})

    assert response.status_code == 422
    assert "nope" in response.json()["detail"]


def test_saving_rejects_a_repeated_group(client):
    response = client.put(
        "/api/bookings",
        json={"bookings": [{"group_code": "MUS021"}, {"group_code": "MUS021"}]},
    )

    assert response.status_code == 422


def test_saving_rejects_going_over_the_activity_limit(client):
    bookings = [{"group_code": f"MUS0{n:02d}"} for n in range(10, 17)]

    response = client.put("/api/bookings", json={"bookings": bookings})

    assert response.status_code == 422
    assert "6" in response.json()["detail"]


def test_a_failed_fetch_without_cache_is_reported_as_upstream_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    app = create_app(config_path=config_path, store=ScheduleStore(lambda config: None))

    response = TestClient(app, raise_server_exceptions=False).get("/api/schedule")

    assert response.status_code == 502


def test_a_failed_refresh_keeps_serving_the_cached_table(client, monkeypatch):
    client.get("/api/schedule")

    from upv_auto.adapters.web import api

    monkeypatch.setattr(
        api.ScheduleStore, "_fetch", staticmethod(lambda config: None), raising=False
    )
    body = client.get("/api/schedule", params={"refresh": "true"}).json()

    assert body["days"][0]["name"] == "Lunes"


def test_demo_mode_is_announced_in_every_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    app = create_app(
        config_path=config_path, store=ScheduleStore(lambda config: GROUPS), demo=True
    )
    client = TestClient(app)

    assert client.get("/api/config").json()["demo"] is True
    assert client.get("/api/schedule").json()["demo"] is True


def test_real_mode_says_the_data_is_not_a_sample(client):
    assert client.get("/api/config").json()["demo"] is False
    assert client.get("/api/schedule").json()["demo"] is False


def _raise(error: Exception):
    def fetch(config):
        raise error

    return fetch


def test_a_missing_playwright_browser_becomes_an_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    failure = RuntimeError(
        "BrowserType.launch: Executable doesn't exist at C:/…/chrome-headless-shell.exe"
    )
    app = create_app(config_path=config_path, store=ScheduleStore(_raise(failure)))

    response = TestClient(app, raise_server_exceptions=False).get("/api/schedule")

    assert response.status_code == 502
    assert "playwright install chromium" in response.json()["detail"]


def test_an_unexpected_failure_does_not_leak_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    app = create_app(config_path=config_path, store=ScheduleStore(_raise(ValueError("boom"))))

    response = TestClient(app, raise_server_exceptions=False).get("/api/schedule")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ValueError" in detail and "boom" not in detail
