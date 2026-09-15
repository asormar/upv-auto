"""Use case: log in, verify the session, and notify the outcome."""

from __future__ import annotations

import logging

from upv_auto.domain.errors import AuthenticationBlocked, AuthenticationFailed
from upv_auto.domain.models import Credentials
from upv_auto.ports import Authenticator, Notifier, SessionVerifier

logger = logging.getLogger(__name__)


def check_login(
    credentials: Credentials,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
) -> bool:
    """Attempt a login and session verification. Returns True iff both succeed."""
    try:
        session = authenticator.login(credentials)
    except AuthenticationBlocked as exc:
        logger.warning("Login blocked: %s", exc)
        notifier.notify(f"Login blocked (captcha/2FA/unexpected page): {exc}")
        return False
    except AuthenticationFailed as exc:
        logger.warning("Login failed: %s", exc)
        notifier.notify(f"Login failed: {exc}")
        return False

    if not verifier.is_valid(session):
        logger.warning("Session verification failed after login")
        notifier.notify("Login appeared to succeed but session verification failed.")
        return False

    logger.info("Login check OK")
    notifier.notify("Login check OK: session is valid.")
    return True
