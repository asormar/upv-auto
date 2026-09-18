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
class LimitsConfig:
    """How many places UPV lets one person hold at the same time.

    Defaults match the Área de Deportes rules: at most 10 activity sessions,
    of which at most 6 may be of this activity.
    """

    max_sessions: int = 10
    max_per_activity: int = 6


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    upv: UpvConfig
    window: WindowConfig
    activity: Activity
    bookings: list[BookingTarget]
    credentials: Credentials
    email: EmailConfig | None
    limits: LimitsConfig = field(default_factory=LimitsConfig)


def load_env_file(path: str | Path = ".env") -> None:
    """Load `KEY=value` lines from a .env file into the environment.

    Real environment variables always win, so CI (where secrets arrive as
    environment variables) is unaffected. Written by hand rather than pulling
    in python-dotenv: the file format we need is three lines of parsing.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


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
    # An empty queue is allowed: a week you are not booking anything.
    bookings = [_parse_booking(b) for b in bookings_raw or []]

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

    limits_raw = raw.get("limits") or {}
    limits = LimitsConfig(
        max_sessions=int(limits_raw.get("max_sessions", LimitsConfig.max_sessions)),
        max_per_activity=int(limits_raw.get("max_per_activity", LimitsConfig.max_per_activity)),
    )

    return AppConfig(
        timezone=timezone,
        upv=upv,
        window=window,
        activity=activity,
        bookings=bookings,
        credentials=credentials,
        email=email,
        limits=limits,
    )


def render_bookings(bookings: list[BookingTarget]) -> str:
    """Render booking targets as the YAML block `load_config` reads back."""
    if not bookings:
        return "bookings: []\n"
    lines = ["bookings:"]
    for target in bookings:
        preferred, *alternatives = target.options
        lines.append(f"  - group_code: {preferred.group_code}")
        if alternatives:
            codes = ", ".join(slot.group_code for slot in alternatives)
            lines.append(f"    alternatives: [{codes}]")
    return "\n".join(lines) + "\n"


def save_bookings(path: str | Path, bookings: list[BookingTarget]) -> None:
    """Replace the `bookings:` block of a config file, leaving the rest as it is.

    Everything else in the file — comments, key order, formatting — is kept
    byte for byte, which a YAML round-trip would not do. An empty list is
    valid: it means nothing gets booked this Saturday.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    original = config_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    start = next((i for i, line in enumerate(lines) if line.startswith("bookings:")), None)
    if start is None:
        updated = original if original.endswith("\n") else original + "\n"
        updated += "\n" + render_bookings(bookings)
    else:
        end = len(lines)
        for i in range(start + 1, len(lines)):
            stripped = lines[i]
            # A new top-level key ends the block; indented lines, comments and
            # blank lines belong to it.
            if stripped.strip() and not stripped[0].isspace() and not stripped.startswith("#"):
                end = i
                break
        updated = "".join(lines[:start]) + render_bookings(bookings) + "".join(lines[end:])

    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(updated, encoding="utf-8")
    temp_path.replace(config_path)
