"""Notifier adapters: a Telegram bot message, with a console fallback."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    """Fallback notifier used when Telegram env vars are not configured."""

    def notify(self, text: str) -> None:
        logger.info("NOTIFY: %s", text)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, *, timeout: float = 10.0) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._timeout = timeout

    def notify(self, text: str) -> None:
        try:
            response = httpx.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to send Telegram notification")
