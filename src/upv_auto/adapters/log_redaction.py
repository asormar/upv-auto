"""Log hygiene for multi-user commands (`book-all`, `refresh`).

Public repository logs must never carry per-user identifying information
(platform-operations spec's "Public Log Hygiene", credential-custody's "No
Plaintext in Logs"). `RedactingFilter` scrubs every log record before it
reaches a handler; `mask_for_actions` additionally emits a GitHub Actions
`::add-mask::` line for a value the moment it becomes known, so it is masked
even in a log line this filter never anticipated.
"""

from __future__ import annotations

import logging
import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_GROUP_CODE_RE = re.compile(r"\b[A-Z]{3}\d{3}\b")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class RedactingFilter(logging.Filter):
    """Scrubs registered secrets and structural patterns from every log record.

    Registered secrets (exact strings — a user's unsealed username or
    password, for instance) are replaced with `***`. Group codes, email
    addresses, and UUIDs are replaced by a `[kind]` placeholder so a log
    line still says *something* happened without saying to whom.
    """

    def __init__(self) -> None:
        super().__init__()
        self._secrets: set[str] = set()

    def register(self, *values: str | None) -> None:
        """Register plaintext values that must never appear in a log record."""
        for value in values:
            if value:
                self._secrets.add(value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = self._redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        text = _UUID_RE.sub("[id]", text)
        text = _EMAIL_RE.sub("[email]", text)
        text = _GROUP_CODE_RE.sub("[group]", text)
        return text


def configure_log_hygiene(filter_: RedactingFilter) -> None:
    """Attach `filter_` to the root logger, and quiet the noisy `httpx` logger.

    Attaching to the *logger* (not just its handlers) means every handler —
    including ones added later, and pytest's own `caplog` handler — sees the
    already-redacted record. `httpx` logs full request URLs at INFO, which
    for this codebase's PostgREST traffic can contain user ids; WARNING and
    above only.
    """
    logging.getLogger().addFilter(filter_)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def mask_for_actions(*values: str | None) -> None:
    """Print a GitHub Actions `::add-mask::` line for each non-empty value.

    Defense in depth: masks the raw value in the Actions UI/log download the
    moment it is known, on top of (not instead of) `RedactingFilter`.
    """
    for value in values:
        if value:
            print(f"::add-mask::{value}")
