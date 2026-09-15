"""Real clock adapter, timezone-aware."""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo


class SystemClock:
    """Wall-clock time in a given IANA timezone (default Europe/Madrid)."""

    def __init__(self, timezone: str = "Europe/Madrid") -> None:
        self._tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)
