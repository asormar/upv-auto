from __future__ import annotations

import pytest

from upv_auto.config import ConfigError, load_config
from upv_auto.domain.models import Credentials

CONFIG_YAML = """
timezone: Europe/Madrid

upv:
  entry_url: https://example.test/entry
  session_check_url: https://example.test/entry

window:
  weekday: saturday
  opens_at: "10:00:00"
  closes_at: "10:03:00"
  retry_interval_seconds: 1.5

slots:
  - facility: "Padel"
    sport: "Padel"
    day_offset_days: 0
    start_time: "18:00"
  - facility: "Padel"
    sport: "Padel"
    day_offset_days: 0
    start_time: "19:00"
"""


def write_config(tmp_path, content: str = CONFIG_YAML):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_load_config_reads_yaml_and_env(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)

    config = load_config(config_path)

    assert config.timezone == "Europe/Madrid"
    assert config.upv.entry_url == "https://example.test/entry"
    assert config.window.opens_at == "10:00:00"
    assert config.window.retry_interval_seconds == 1.5
    assert len(config.slots) == 2
    assert config.slots[0].start_time == "18:00"
    assert config.credentials.username == "student1"
    assert config.credentials.password == "hunter2"
    assert config.email is None


def test_load_config_builds_email_config_defaulting_recipient_to_sender(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    monkeypatch.setenv("SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("NOTIFY_EMAIL_TO", raising=False)

    config = load_config(config_path)

    assert config.email is not None
    assert config.email.username == "me@gmail.com"
    assert config.email.recipient == "me@gmail.com"
    assert "abcd" not in repr(config.email)


def test_load_config_uses_explicit_email_recipient(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    monkeypatch.setenv("SMTP_USERNAME", "me@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "secret")
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "other@upv.es")

    config = load_config(config_path)

    assert config.email.recipient == "other@upv.es"


def test_load_config_missing_required_env_raises_clear_error(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    monkeypatch.delenv("UPV_USERNAME", raising=False)
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")

    with pytest.raises(ConfigError, match="UPV_USERNAME"):
        load_config(config_path)


def test_load_config_missing_file_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")

    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "does-not-exist.yaml")


def test_credentials_repr_hides_password():
    credentials = Credentials(username="student1", password="hunter2")

    text = repr(credentials)

    assert "student1" in text
    assert "hunter2" not in text
