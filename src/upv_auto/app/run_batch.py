"""Use case: the Saturday multi-user batch (weekly-batch-booking spec).

Processes every user with a non-empty queue in one GitHub Actions run.
`BookSlotUseCase` is reused untouched, once per user, each in its own
thread; `TurnScheduler`/`TurnTakingClock` (see `app.turns`) make sure no two
users ever interact with UPV at the same time. A failure in one user's
thread — login rejected, an unsealable credential, an unexpected exception —
is recorded for that user only and never aborts the others (per-user
failure isolation). Each user's outcome is buffered (`BufferedNotifier`) and
only actually sent, one at a time, after every thread has joined, so SMTP
stays out of the turn-taking window.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from contextlib import AbstractContextManager
from typing import Callable

from upv_auto.app.book_slot import BookSlotUseCase
from upv_auto.app.turns import BufferedNotifier, TurnScheduler, TurnTakingClock
from upv_auto.config import AppConfig
from upv_auto.domain.errors import CredentialsUnavailable
from upv_auto.domain.models import Credentials, UserRecord
from upv_auto.ports import (
    ActivityTableClient,
    Authenticator,
    Clock,
    CredentialOpener,
    Notifier,
    SessionVerifier,
    UserDirectory,
)

logger = logging.getLogger(__name__)

AuthenticatorFactory = Callable[[AppConfig], Authenticator]
VerifierFactory = Callable[[AppConfig], SessionVerifier]
TableClientFactory = Callable[[AppConfig], AbstractContextManager[ActivityTableClient]]
NotifierFactory = Callable[[UserRecord], Notifier]
OnCredentialsOpened = Callable[[Credentials], None]


def run_batch(
    config: AppConfig,
    directory: UserDirectory,
    credential_opener: CredentialOpener,
    authenticator_factory: AuthenticatorFactory,
    verifier_factory: VerifierFactory,
    table_client_factory: TableClientFactory,
    notifier_factory: NotifierFactory,
    clock: Clock,
    run_id: str,
    *,
    skip_wait: bool = False,
    on_credentials_opened: OnCredentialsOpened | None = None,
) -> int:
    """Run the batch. Returns 0 iff every user in the roster got everything they queued.

    `on_credentials_opened` is called the moment a user's credentials are
    unsealed (before any login attempt) — the CLI uses it to register the
    plaintext with `RedactingFilter` and emit GitHub Actions `::add-mask::`
    lines, keeping this use case free of any adapter import.
    """
    roster = directory.roster()
    total = len(roster)
    if total == 0:
        logger.info("Batch roster is empty: nothing to do")
        return 0

    scheduler = TurnScheduler([user.user_id for user in roster])
    notifiers: dict[str, BufferedNotifier] = {}
    all_ok = True
    lock = threading.Lock()

    def worker(user: UserRecord, index: int) -> None:
        nonlocal all_ok
        notifier = BufferedNotifier()
        ok = _process_user(
            user,
            index,
            total,
            notifier=notifier,
            config=config,
            directory=directory,
            credential_opener=credential_opener,
            scheduler=scheduler,
            clock=clock,
            authenticator_factory=authenticator_factory,
            verifier_factory=verifier_factory,
            table_client_factory=table_client_factory,
            run_id=run_id,
            skip_wait=skip_wait,
            on_credentials_opened=on_credentials_opened,
        )
        with lock:
            notifiers[user.user_id] = notifier
            if not ok:
                all_ok = False

    threads = [
        threading.Thread(target=worker, args=(user, index))
        for index, user in enumerate(roster, start=1)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # SMTP happens here, sequentially, one real send per user, entirely
    # outside the turn-taking window (design.md's "Notification" decision).
    for user in roster:
        try:
            notifier_factory(user).notify(notifiers[user.user_id].combined())
        except Exception as exc:  # a failed send must not hide the others
            logger.error("Failed to send the batch email for one user: %s", type(exc).__name__)

    return 0 if all_ok else 1


def _process_user(
    user: UserRecord,
    index: int,
    total: int,
    *,
    notifier: BufferedNotifier,
    config: AppConfig,
    directory: UserDirectory,
    credential_opener: CredentialOpener,
    scheduler: TurnScheduler,
    clock: Clock,
    authenticator_factory: AuthenticatorFactory,
    verifier_factory: VerifierFactory,
    table_client_factory: TableClientFactory,
    run_id: str,
    skip_wait: bool,
    on_credentials_opened: OnCredentialsOpened | None,
) -> bool:
    """Process one user's turn end to end. Always records a result; never raises.

    `label` names the user only as an opaque index (platform-operations
    spec's "Public Log Hygiene"): logs never carry `user.user_id` or
    `user.email` directly.
    """
    label = f"user {index}/{total}"
    status = "error"
    ok = False

    try:
        credentials = credential_opener.open(user.sealed_credentials, user.key_id)
        if on_credentials_opened is not None:
            on_credentials_opened(credentials)

        user_config = dataclasses.replace(
            config, credentials=credentials, bookings=user.bookings, email=None
        )
        turn_clock = TurnTakingClock(user.user_id, scheduler, clock)

        with table_client_factory(user_config) as table_client:
            authenticator = authenticator_factory(user_config)
            verifier = verifier_factory(user_config)

            # The turn is acquired here (covers login too) and released
            # internally by `turn_clock.sleep()` for the rest of the run.
            scheduler.acquire(user.user_id)
            use_case = BookSlotUseCase(
                authenticator=authenticator,
                verifier=verifier,
                table_client=table_client,
                notifier=notifier,
                clock=turn_clock,
                config=user_config,
            )
            exit_code = use_case.execute(skip_wait=skip_wait)

        status = "booked" if exit_code == 0 else "incomplete"
        ok = exit_code == 0
    except CredentialsUnavailable:
        logger.warning("%s: credentials unavailable, skipping", label)
        status = "credentials_unavailable"
        notifier.notify(
            "Could not unseal your UPV credentials (unknown or rotated key). "
            "Please re-enter them."
        )
    except Exception as exc:  # per-user isolation: one bad user must not abort the batch
        logger.error("%s: unexpected error: %s", label, type(exc).__name__)
        status = "error"
        notifier.notify(f"Unexpected error while processing your booking: {type(exc).__name__}.")
    finally:
        # Always leave the rotation, whether or not this user ever acquired
        # a turn — otherwise a user who fails before `scheduler.acquire()`
        # would permanently block whoever is queued behind them.
        scheduler.finish(user.user_id)

    logger.info("%s: finished with status %s", label, status)
    directory.record_result(user.user_id, run_id, status, notifier.combined())
    return ok
