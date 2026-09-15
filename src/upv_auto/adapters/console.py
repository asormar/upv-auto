"""Fallback notifier that writes to the log."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    """Used when email settings are not configured."""

    def notify(self, text: str) -> None:
        logger.info("NOTIFY: %s", text)
