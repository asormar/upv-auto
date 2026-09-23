from __future__ import annotations

from pathlib import Path

import pytest

from upv_auto.config import (
    ConfigError,
    load_config,
    load_env_file,
    parse_booking_spec,
    save_bookings,
)
from upv_auto.domain.models import BookingTarget, Credentials, Slot

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

activity:
  name: MUSCULACION
  campus: V
  tipoact: "6894"
  codacti: "21948"

bookings:
  - group_code: MUS074
    alternatives: [MUS075]
  - group_code: MUS021
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
    assert config.activity.campus == "V"
    assert config.activity.codacti == "21948"
    assert len(config.bookings) == 2
    assert [s.group_code for s in config.bookings[0].options] == ["MUS074", "MUS075"]
    assert config.bookings[1].label == "MUS021"
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


def test_load_config_require_upv_credentials_false_skips_the_env_requirement(tmp_path, monkeypatch):
    """`book-all` has no single shared UPV login (see `app.run_batch`)."""
    config_path = write_config(tmp_path)
    monkeypatch.delenv("UPV_USERNAME", raising=False)
    monkeypatch.delenv("UPV_PASSWORD", raising=False)

    config = load_config(config_path, require_upv_credentials=False)

    assert config.credentials == Credentials(username="", password="")


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


def test_load_config_invalid_group_code_raises_clear_error(tmp_path, monkeypatch):
    config_path = write_config(tmp_path, CONFIG_YAML.replace("MUS074", "not-a-code"))
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")

    with pytest.raises(ConfigError, match="not-a-code"):
        load_config(config_path)


def test_credentials_repr_hides_password():
    credentials = Credentials(username="student1", password="hunter2")

    text = repr(credentials)

    assert "student1" in text
    assert "hunter2" not in text


def test_parse_booking_spec_supports_alternatives_and_validates_codes():
    target = parse_booking_spec("MUS022, MUS037")

    assert [s.group_code for s in target.options] == ["MUS022", "MUS037"]
    with pytest.raises(ConfigError, match="bad"):
        parse_booking_spec("MUS022,bad")


def _write_config(tmp_path, bookings_block: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "timezone: Europe/Madrid\n"
        "\n"
        "upv:\n"
        "  entry_url: https://example.test/entry\n"
        "  session_check_url: https://example.test/check\n"
        "\n"
        "window:\n"
        "  weekday: saturday\n"
        "  opens_at: '10:01:00'\n"
        "  closes_at: '10:04:00'\n"
        "  retry_interval_seconds: 1.5\n"
        "\n"
        "activity:\n"
        "  name: MUSCULACION\n"
        "  campus: V\n"
        "  tipoact: '6894'\n"
        "  codacti: '21948'\n"
        "\n"
        "# Keep this comment\n" + bookings_block,
        encoding="utf-8",
    )
    return config_path


def test_save_bookings_rewrites_only_the_bookings_block(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = _write_config(tmp_path, "bookings:\n  - group_code: MUS021 # midday\n")

    save_bookings(
        config_path,
        [
            BookingTarget(options=(Slot("MUS022"), Slot("MUS037"))),
            BookingTarget(options=(Slot("MUS074"),)),
        ],
    )

    text = config_path.read_text(encoding="utf-8")
    assert "# Keep this comment" in text
    assert "timezone: Europe/Madrid" in text
    assert "MUS021" not in text
    reloaded = load_config(config_path)
    assert [[s.group_code for s in t.options] for t in reloaded.bookings] == [
        ["MUS022", "MUS037"],
        ["MUS074"],
    ]


def test_save_bookings_keeps_keys_that_follow_the_block(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = _write_config(
        tmp_path,
        "bookings:\n  - group_code: MUS021\n\nlimits:\n  max_sessions: 10\n  max_per_activity: 6\n",
    )

    save_bookings(config_path, [BookingTarget(options=(Slot("MUS022"),))])

    reloaded = load_config(config_path)
    assert reloaded.limits.max_per_activity == 6
    assert [s.group_code for t in reloaded.bookings for s in t.options] == ["MUS022"]


def test_an_empty_queue_round_trips(tmp_path, monkeypatch):
    """Clearing the queue is a normal state: a week you are not booking."""
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = _write_config(tmp_path, "bookings:\n  - group_code: MUS021\n")

    save_bookings(config_path, [])

    assert load_config(config_path).bookings == []


def test_limits_default_to_the_upv_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("UPV_USERNAME", "student1")
    monkeypatch.setenv("UPV_PASSWORD", "hunter2")
    config_path = _write_config(tmp_path, "bookings:\n  - group_code: MUS021\n")

    config = load_config(config_path)

    assert (config.limits.max_sessions, config.limits.max_per_activity) == (10, 6)


def test_load_env_file_fills_missing_variables_only(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# a comment\n"
        "UPV_USERNAME=from-file\n"
        "UPV_PASSWORD = 'quoted secret'\n"
        "\n"
        "NOT_A_PAIR\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("UPV_USERNAME", "from-shell")
    monkeypatch.delenv("UPV_PASSWORD", raising=False)

    load_env_file(env_path)

    import os

    assert os.environ["UPV_USERNAME"] == "from-shell"
    assert os.environ["UPV_PASSWORD"] == "quoted secret"


def test_load_env_file_without_a_file_is_a_no_op(tmp_path):
    load_env_file(tmp_path / "missing.env")
