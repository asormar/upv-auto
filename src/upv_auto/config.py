"""Configuration loading.

Behaviour (URLs, window timing, slots) comes from a YAML file. Secrets
(credentials, notifier tokens) come from environment variables only, so they
never end up committed to the repository.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from upv_auto.domain.models import Activity, BookingTarget, Credentials, Slot


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid, with a human-readable message."""


_GROUP_CODE_RE = re.compile(r"^[A-Z]{3}\d{3}$")


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
    activity: Activity
    bookings: list[BookingTarget]
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


def _parse_booking(booking_raw: dict) -> BookingTarget:
    codes = [str(_require_key(booking_raw, "group_code"))]
    codes += [str(code) for code in booking_raw.get("alternatives") or []]
    return BookingTarget(options=tuple(Slot(group_code=validate_group_code(c)) for c in codes))


def parse_booking_spec(spec: str) -> BookingTarget:
    """Parse 'MUS021' or 'MUS021,MUS036' (preferred first, then alternatives)."""
    codes = [code.strip() for code in spec.split(",") if code.strip()]
    if not codes:
        raise ConfigError(f"Empty booking spec: '{spec}'")
    return BookingTarget(options=tuple(Slot(group_code=validate_group_code(c)) for c in codes))


def validate_group_code(group_code: str) -> str:
    if not _GROUP_CODE_RE.match(group_code):
        raise ConfigError(
            f"Invalid group_code '{group_code}': expected a UPV group code like 'MUS074'"
        )
    return group_code


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
    activity_raw = _require_key(raw, "activity")
    bookings_raw = _require_key(raw, "bookings")

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
    activity = Activity(
        campus=str(_require_key(activity_raw, "campus")),
        tipoact=str(_require_key(activity_raw, "tipoact")),
        codacti=str(_require_key(activity_raw, "codacti")),
        name=str(_require_key(activity_raw, "name")),
    )
    bookings = [_parse_booking(b) for b in bookings_raw]
    if not bookings:
        raise ConfigError("Config key 'bookings' must list at least one booking")

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
        activity=activity,
        bookings=bookings,
        credentials=credentials,
        email=email,
    )
