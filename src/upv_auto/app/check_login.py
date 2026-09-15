"""Use case: log in, verify the session, and notify the outcome."""

from __future__ import annotations

import logging

from upv_auto.app.authenticate import authenticate
from upv_auto.domain.models import Credentials
from upv_auto.ports import Authenticator, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)


def check_login(
    credentials: Credentials,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
) -> bool:
    """Attempt a login and session verification. Returns True iff both succeed."""
    session = authenticate(credentials, authenticator, verifier, notifier, clock)
    if session is None:
        return False

    logger.info("Login check OK")
    notifier.notify("Login check OK: session is valid.")
    return True
