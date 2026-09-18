"""Web adapter: a small HTTP API over the existing use cases.

It is a driver, like the CLI: it builds the same adapters, calls the same use
cases, and never reaches into the domain. Logging into UPV is slow (a real
browser), so a fetched table is cached in memory and only refreshed on
request.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from upv_auto.adapters.console import ConsoleNotifier
from upv_auto.adapters.httpx_booking import HttpxActivityTableClient
from upv_auto.adapters.httpx_session import HttpxSessionVerifier
from upv_auto.adapters.playwright_auth import PlaywrightCasAuthenticator
from upv_auto.adapters.system_clock import SystemClock
from upv_auto.adapters.web.schedule_view import build_days, count_enrolled_now, count_queued
from upv_auto.app.fetch_schedule import fetch_schedule
from upv_auto.config import AppConfig, ConfigError, load_config, save_bookings, validate_group_code
from upv_auto.domain.models import BookingTarget, GroupAvailability, Slot

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=10)


class BookingIn(BaseModel):
    group_code: str
    alternatives: list[str] = Field(default_factory=list)


class BookingsIn(BaseModel):
    bookings: list[BookingIn]


def _explain(error: Exception) -> str:
    """Turn an adapter failure into something the user can act on."""
    text = str(error)
    if "Executable doesn't exist" in text or "playwright install" in text:
        return (
            "Falta el navegador de Playwright. Ejecuta: "
            "python -m playwright install chromium"
        )
    return f"No se pudo leer la tabla de la UPV: {type(error).__name__}. Mira la consola."


@dataclass
class _CachedSchedule:
    groups: dict[str, GroupAvailability]
    fetched_at: datetime


class ScheduleStore:
    """Holds the last fetched table so the UI does not log in on every request."""

    def __init__(self, fetch: Callable[[AppConfig], dict[str, GroupAvailability] | None]):
        self._fetch = fetch
        self._lock = threading.Lock()
        self._cached: _CachedSchedule | None = None

    def get(self, config: AppConfig, refresh: bool = False) -> _CachedSchedule:
        with self._lock:
            fresh_enough = (
                self._cached is not None
                and datetime.now() - self._cached.fetched_at < CACHE_TTL
            )
            if self._cached is not None and fresh_enough and not refresh:
                return self._cached

            reason = ""
            try:
                groups = self._fetch(config)
            except Exception as error:  # noqa: BLE001 - any adapter failure is a bad gateway
                logger.exception("Reading the UPV table failed")
                groups = None
                reason = _explain(error)

            if groups is None:
                if self._cached is not None:
                    return self._cached
                raise HTTPException(
                    status_code=502,
                    detail=reason
                    or "No se pudo leer la tabla de la UPV. Revisa el acceso y reintenta.",
                )
            self._cached = _CachedSchedule(groups=groups, fetched_at=datetime.now())
            return self._cached


def _fetch_from_upv(config: AppConfig) -> dict[str, GroupAvailability] | None:
    with HttpxActivityTableClient(activity=config.activity) as table_client:
        return fetch_schedule(
            config,
            PlaywrightCasAuthenticator(entry_url=config.upv.entry_url),
            HttpxSessionVerifier(session_check_url=config.upv.session_check_url),
            ConsoleNotifier(),
            SystemClock(timezone=config.timezone),
            table_client,
        )


def _bookings_payload(config: AppConfig) -> list[dict[str, Any]]:
    return [
        {
            "group_code": target.options[0].group_code,
            "alternatives": [slot.group_code for slot in target.options[1:]],
        }
        for target in config.bookings
    ]


def _to_targets(payload: BookingsIn) -> list[BookingTarget]:
    targets = []
    for booking in payload.bookings:
        codes = [booking.group_code, *booking.alternatives]
        try:
            slots = tuple(Slot(group_code=validate_group_code(code.strip())) for code in codes)
        except ConfigError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        targets.append(BookingTarget(options=slots))
    return targets


def create_app(
    config_path: str | Path = "config.yaml",
    store: ScheduleStore | None = None,
    static_dir: str | Path | None = None,
    demo: bool = False,
) -> FastAPI:
    """Build the API. `store` is injectable so tests never touch the network.

    `demo` marks every response as sample data, so the UI can say so out loud:
    sample groups look exactly like real ones and must never be mistaken for
    the user's actual enrolments.
    """
    app = FastAPI(title="upv-auto", docs_url="/api/docs", openapi_url="/api/openapi.json")
    schedule_store = store or ScheduleStore(_fetch_from_upv)

    def current_config() -> AppConfig:
        try:
            return load_config(config_path)
        except ConfigError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.get("/api/config")
    def read_config() -> dict[str, Any]:
        config = current_config()
        return {
            "activity": asdict(config.activity),
            "window": asdict(config.window),
            "timezone": config.timezone,
            "limits": asdict(config.limits),
            "bookings": _bookings_payload(config),
            "email_notifications": config.email is not None,
            "demo": demo,
        }

    @app.get("/api/schedule")
    def read_schedule(refresh: bool = False) -> dict[str, Any]:
        config = current_config()
        cached = schedule_store.get(config, refresh=refresh)
        days = build_days(cached.groups, config.bookings)
        return {
            "demo": demo,
            "fetched_at": cached.fetched_at.isoformat(timespec="seconds"),
            "activity": asdict(config.activity),
            "limits": {
                **asdict(config.limits),
                # What Saturday would book, which is what the limit is about
                # here, kept apart from this week's enrolments.
                "queued": count_queued(config.bookings),
                "enrolled_this_week": count_enrolled_now(cached.groups),
            },
            "days": [
                {"name": day.name, "slots": [asdict(slot) for slot in day.slots]}
                for day in days
            ],
        }

    @app.put("/api/bookings")
    def write_bookings(payload: BookingsIn) -> dict[str, Any]:
        config = current_config()
        targets = _to_targets(payload)
        preferred = [target.options[0].group_code for target in targets]
        if len(set(preferred)) != len(preferred):
            raise HTTPException(status_code=422, detail="Hay un grupo repetido en la cola.")
        if len(targets) > config.limits.max_per_activity:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"La UPV permite {config.limits.max_per_activity} sesiones de esta "
                    "actividad a la vez."
                ),
            )
        try:
            save_bookings(config_path, targets)
        except ConfigError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"bookings": _bookings_payload(current_config())}

    if static_dir is not None:
        root = Path(static_dir)
        if root.is_dir():
            app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

            @app.get("/")
            def index() -> FileResponse:
                return FileResponse(root / "index.html")

    return app
