"""Notifier adapter that sends an email through an SMTP server (Gmail by default)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SUBJECT_PREFIX = "[upv-auto]"


class EmailNotifier:
    def __init__(
        self,
        username: str,
        app_password: str,
        recipient: str,
        *,
        host: str = "smtp.gmail.com",
        port: int = 465,
        timeout: float = 15.0,
    ) -> None:
        self._username = username
        # Gmail displays app passwords in groups separated by spaces.
        self._app_password = app_password.replace(" ", "")
        self._recipient = recipient
        self._host = host
        self._port = port
        self._timeout = timeout

    def notify(self, text: str) -> None:
        message = EmailMessage()
        message["Subject"] = f"{SUBJECT_PREFIX} {text.splitlines()[0] if text else 'Notification'}"
        message["From"] = self._username
        message["To"] = self._recipient
        message.set_content(text)

        try:
            with smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.login(self._username, self._app_password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # Log only the exception type and message; never the credentials.
            logger.error("Failed to send email notification: %s: %s", type(exc).__name__, exc)
