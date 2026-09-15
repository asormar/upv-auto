"""Shared login step: authenticate, verify the session, retry transient failures.

Only transient problems are retried (server unavailable, session that does not
verify). Rejected credentials and captcha/2FA stop immediately: retrying those
could lock the account or look like an attack.
"""

from __future__ import annotations

import logging

from upv_auto.domain.errors import (
    AuthenticationBlocked,
    AuthenticationFailed,
    AuthenticationUnavailable,
)
from upv_auto.domain.models import Credentials, Session
from upv_auto.ports import Authenticator, Clock, Notifier, SessionVerifier

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 10.0


def authenticate(
    credentials: Credentials,
    authenticator: Authenticator,
    verifier: SessionVerifier,
    notifier: Notifier,
    clock: Clock,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
) -> Session | None:
    """Return a verified Session, or None after notifying why login failed."""
    last_problem = ""

    for attempt in range(1, max_attempts + 1):
        try:
            session = authenticator.login(credentials)
        except AuthenticationBlocked as exc:
            logger.warning("Login blocked: %s", exc)
            notifier.notify(f"Login blocked (captcha/2FA/unexpected page): {exc}")
            return None
        except AuthenticationFailed as exc:
            logger.warning("Login failed: %s", exc)
            notifier.notify(f"Login failed: {exc}")
            return None
        except AuthenticationUnavailable as exc:
            last_problem = f"UPV unavailable: {exc}"
        else:
            if verifier.is_valid(session):
                return session
            last_problem = "session verification failed"

        if attempt < max_attempts:
            logger.warning(
                "Login attempt %d/%d failed (%s); retrying in %.0fs",
                attempt,
                max_attempts,
                last_problem,
                retry_delay_seconds,
            )
            clock.sleep(retry_delay_seconds)

    logger.error("Login failed after %d attempt(s): %s", max_attempts, last_problem)
    notifier.notify(f"Login failed after {max_attempts} attempt(s): {last_problem}")
    return None
