"""Configuration loading.

Behaviour (URLs, window timing, slots) comes from a YAML file. Secrets
(credentials, notifier tokens) come from environment variables only, so they
never end up committed to the repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from upv_auto.domain.models import Credentials, Slot


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid, with a human-readable message."""


@dataclass(frozen=True)
class UpvConfig:
    entry_url: str
    session_check_url: str


@dataclass(frozen=True)
class WindowConfig:
    weekday: str
    opens_at: str
    closes_at: str
    retry_interval_seconds: float


@dataclass(frozen=True)
class EmailConfig:
    username: str
    app_password: str = field(repr=False)
    recipient: str


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    upv: UpvConfig
    window: WindowConfig
    slots: list[Slot]
    credentials: Credentials
    email: EmailConfig | None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            "Set it in your shell, in a .env file loaded before running, "
            "or as a GitHub Actions secret."
        )
    return value


def _require_key(raw: dict, key: str) -> object:
    if key not in raw:
        raise ConfigError(f"Missing required config key: '{key}'")
    return raw[key]


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load YAML config from `path` and merge in secrets from the environment."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    timezone = _require_key(raw, "timezone")
    upv_raw = _require_key(raw, "upv")
    window_raw = _require_key(raw, "window")
    slots_raw = _require_key(raw, "slots")

    upv = UpvConfig(
        entry_url=_require_key(upv_raw, "entry_url"),
        session_check_url=_require_key(upv_raw, "session_check_url"),
    )
    window = WindowConfig(
        weekday=_require_key(window_raw, "weekday"),
        opens_at=_require_key(window_raw, "opens_at"),
        closes_at=_require_key(window_raw, "closes_at"),
        retry_interval_seconds=float(_require_key(window_raw, "retry_interval_seconds")),
    )
    slots = [
        Slot(
            facility=_require_key(s, "facility"),
            sport=_require_key(s, "sport"),
            day_offset_days=int(_require_key(s, "day_offset_days")),
            start_time=_require_key(s, "start_time"),
        )
        for s in slots_raw
    ]

    credentials = Credentials(
        username=_require_env("UPV_USERNAME"),
        password=_require_env("UPV_PASSWORD"),
    )

    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_app_password = os.environ.get("SMTP_APP_PASSWORD")
    email = (
        EmailConfig(
            username=smtp_username,
            app_password=smtp_app_password,
            # Defaults to emailing yourself.
            recipient=os.environ.get("NOTIFY_EMAIL_TO") or smtp_username,
        )
        if smtp_username and smtp_app_password
        else None
    )

    return AppConfig(
        timezone=timezone,
        upv=upv,
        window=window,
        slots=slots,
        credentials=credentials,
        email=email,
    )
