"""Command-line entry point.

Usage:
    python -m upv_auto check-login [--config PATH]
    python -m upv_auto list-groups [--config PATH]
    python -m upv_auto book [--config PATH] [--now]
    python -m upv_auto book-all [--config PATH] [--now]
    python -m upv_auto refresh --request-id REQUEST_ID [--config PATH]
    python -m upv_auto seal-keygen [--key-id KEY_ID]
    python -m upv_auto serve [--config PATH] [--host HOST] [--port PORT]

--now skips waiting for the booking window to open; useful for local testing.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from upv_auto.adapters.httpx_booking import HttpxActivityTableClient
from upv_auto.adapters.httpx_session import HttpxSessionVerifier
from upv_auto.adapters.playwright_auth import PlaywrightCasAuthenticator
from upv_auto.adapters.system_clock import SystemClock
from upv_auto.adapters.console import ConsoleNotifier
from upv_auto.adapters.email import EmailNotifier
from upv_auto.app.book_slot import BookSlotUseCase
from upv_auto.app.check_login import check_login
from upv_auto.app.list_groups import list_groups
from upv_auto.config import (
    AppConfig,
    ConfigError,
    load_config,
    load_env_file,
    parse_booking_spec,
)
from upv_auto.domain.models import Credentials, UserRecord

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_notifier(config: AppConfig):
    if config.email is not None:
        return EmailNotifier(
            config.email.username, config.email.app_password, config.email.recipient
        )
    return ConsoleNotifier()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="upv_auto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check-login", help="Log in and verify the session, then exit."
    )
    check_parser.add_argument("--config", default="config.yaml")

    list_groups_parser = subparsers.add_parser(
        "list-groups",
        help="Log in, fetch the activity table, and print each group's state.",
    )
    list_groups_parser.add_argument("--config", default="config.yaml")

    book_parser = subparsers.add_parser(
        "book", help="Wait for the booking window and attempt to book a slot."
    )
    book_parser.add_argument("--config", default="config.yaml")
    book_parser.add_argument(
        "--now",
        action="store_true",
        help="Skip waiting for the window to open (for testing).",
    )
    book_parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        metavar="CODES",
        help=(
            "Booking to make instead of the configured ones: 'MUS021' or 'MUS021,MUS036' "
            "(preferred first, then alternatives). Repeat for several bookings."
        ),
    )

    book_all_parser = subparsers.add_parser(
        "book-all",
        help="Multi-user Saturday batch: every Supabase user with a non-empty queue, turn-taking.",
    )
    book_all_parser.add_argument("--config", default="config.yaml")
    book_all_parser.add_argument(
        "--now",
        action="store_true",
        help="Skip waiting for the window to open (for testing).",
    )

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Fetch and cache one user's schedule for an already-claimed refresh request.",
    )
    refresh_parser.add_argument("--config", default="config.yaml")
    refresh_parser.add_argument(
        "--request-id",
        required=True,
        help="Opaque refresh_requests.id (UUID), set only by the refresh Edge Function.",
    )

    seal_keygen_parser = subparsers.add_parser(
        "seal-keygen", help="Generate a new sealed-box key pair for credential custody."
    )
    seal_keygen_parser.add_argument(
        "--key-id",
        default="v1",
        help="Identifier for the new key pair (used as SEAL_PRIVATE_KEYS' JSON key and VITE_SEAL_KEY_ID).",
    )

    serve_parser = subparsers.add_parser(
        "serve", help="Run the local web UI (needs the 'web' extra installed)."
    )
    serve_parser.add_argument("--config", default="config.yaml")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument(
        "--demo",
        action="store_true",
        help="Serve the sample activity table instead of logging into UPV (for UI work).",
    )

    return parser.parse_args(argv)


def _demo_store():
    """A schedule store backed by the sample table, so the UI can run offline."""
    import os

    from upv_auto.adapters.upv_activities_parser import parse_groups
    from upv_auto.adapters.web.api import ScheduleStore

    os.environ.setdefault("UPV_USERNAME", "demo")
    os.environ.setdefault("UPV_PASSWORD", "demo")
    sample = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "activities_musculacion.html"
    html = sample.read_text(encoding="utf-8", errors="replace")
    groups = parse_groups(html)
    logger.warning("Demo mode: serving the sample activity table, not UPV data")
    return ScheduleStore(lambda config: groups)


def _require_env_var(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _settings_payload(config: AppConfig) -> dict:
    """The `app_settings.settings` shape the web frontend's `getConfig()` reads
    (see `web/src/api/supabase.ts`'s `AppSettingsRow`)."""
    return {
        "activity": {
            "campus": config.activity.campus,
            "tipoact": config.activity.tipoact,
            "codacti": config.activity.codacti,
            "name": config.activity.name,
        },
        "window": {
            "weekday": config.window.weekday,
            "opens_at": config.window.opens_at,
            "closes_at": config.window.closes_at,
            "retry_interval_seconds": config.window.retry_interval_seconds,
        },
        "timezone": config.timezone,
        "limits": {
            "max_sessions": config.limits.max_sessions,
            "max_per_activity": config.limits.max_per_activity,
        },
    }


def _seal_keygen(args: argparse.Namespace) -> int:
    """Generate a fresh sealed-box key pair (credential-custody spec: "Key Rotation
    Invalidates Stored Credentials"). Prints the values to wire up by hand: the
    public half goes to the frontend, the private half to the runner's secret."""
    from upv_auto.adapters.sealed_box import generate_keypair

    public_key, private_key = generate_keypair()
    key_id = args.key_id
    print(f"key_id: {key_id}")
    print(f"VITE_SEAL_PUBLIC_KEY={public_key}")
    print(f"VITE_SEAL_KEY_ID={key_id}")
    print(f'SEAL_PRIVATE_KEYS entry to merge into the existing JSON secret: "{key_id}": "{private_key}"')
    return 0


def _book_all(args: argparse.Namespace) -> int:
    """Multi-user Saturday batch: every Supabase user with a non-empty queue,
    processed turn-taking (weekly-batch-booking spec). Imported lazily so the
    single-user CLI still works without the 'multiuser' extra installed."""
    try:
        from upv_auto.adapters.log_redaction import RedactingFilter, configure_log_hygiene, mask_for_actions
        from upv_auto.adapters.sealed_box import SealedBoxOpener
        from upv_auto.adapters.supabase_rest import SupabaseRestUserDirectory
        from upv_auto.app.run_batch import run_batch
    except ImportError:
        logger.error("book-all needs the extra dependencies: pip install -e \".[multiuser]\"")
        return 1

    try:
        config = load_config(args.config, require_upv_credentials=False)
        supabase_url = _require_env_var("SUPABASE_URL")
        service_role_key = _require_env_var("SUPABASE_SERVICE_ROLE_KEY")
        private_keys = json.loads(_require_env_var("SEAL_PRIVATE_KEYS"))
    except ConfigError as exc:
        logger.error(str(exc))
        return 1
    except json.JSONDecodeError as exc:
        logger.error("SEAL_PRIVATE_KEYS is not valid JSON: %s", exc)
        return 1

    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_app_password = os.environ.get("SMTP_APP_PASSWORD")
    run_id = os.environ.get("GITHUB_RUN_ID") or str(uuid.uuid4())

    redacting_filter = RedactingFilter()
    configure_log_hygiene(redacting_filter)

    def on_credentials_opened(credentials: Credentials) -> None:
        redacting_filter.register(credentials.username, credentials.password)
        mask_for_actions(credentials.username, credentials.password)

    def authenticator_factory(user_config: AppConfig):
        return PlaywrightCasAuthenticator(entry_url=user_config.upv.entry_url)

    def verifier_factory(user_config: AppConfig):
        return HttpxSessionVerifier(session_check_url=user_config.upv.session_check_url)

    def table_client_factory(user_config: AppConfig):
        return HttpxActivityTableClient(activity=user_config.activity)

    def notifier_factory(user: UserRecord):
        if smtp_username and smtp_app_password:
            return EmailNotifier(smtp_username, smtp_app_password, user.email)
        return ConsoleNotifier()

    clock = SystemClock(timezone=config.timezone)

    with SupabaseRestUserDirectory(supabase_url, service_role_key) as directory:
        directory.upsert_settings(_settings_payload(config))
        return run_batch(
            config,
            directory,
            SealedBoxOpener(private_keys),
            authenticator_factory,
            verifier_factory,
            table_client_factory,
            notifier_factory,
            clock,
            run_id,
            skip_wait=args.now,
            on_credentials_opened=on_credentials_opened,
        )


def _refresh(args: argparse.Namespace) -> int:
    """One user's schedule refresh, dispatched by `refresh.yml` with only an
    opaque `request_id` input (design.md's "Refresh dispatch" decision).
    Validates the input is a UUID before it touches anything else — the
    Edge Function and the workflow's own bash step already do the same
    check, but this CLI must never trust an input that reaches it only
    through a GitHub Actions `workflow_dispatch` field (threat matrix:
    workflow-input injection). Imported lazily, mirroring `_book_all`, so
    the single-user CLI still works without the 'multiuser' extra installed.
    """
    try:
        request_id = str(uuid.UUID(args.request_id))
    except ValueError:
        logger.error("Invalid --request-id: expected a UUID")
        return 1

    try:
        from upv_auto.adapters.log_redaction import RedactingFilter, configure_log_hygiene, mask_for_actions
        from upv_auto.adapters.sealed_box import SealedBoxOpener
        from upv_auto.adapters.supabase_rest import SupabaseRestUserDirectory
        from upv_auto.app.refresh_user import refresh_user
    except ImportError:
        logger.error("refresh needs the extra dependencies: pip install -e \".[multiuser]\"")
        return 1

    try:
        config = load_config(args.config, require_upv_credentials=False)
        supabase_url = _require_env_var("SUPABASE_URL")
        service_role_key = _require_env_var("SUPABASE_SERVICE_ROLE_KEY")
        private_keys = json.loads(_require_env_var("SEAL_PRIVATE_KEYS"))
    except ConfigError as exc:
        logger.error(str(exc))
        return 1
    except json.JSONDecodeError as exc:
        logger.error("SEAL_PRIVATE_KEYS is not valid JSON: %s", exc)
        return 1

    redacting_filter = RedactingFilter()
    configure_log_hygiene(redacting_filter)

    def on_credentials_opened(credentials: Credentials) -> None:
        redacting_filter.register(credentials.username, credentials.password)
        mask_for_actions(credentials.username, credentials.password)

    clock = SystemClock(timezone=config.timezone)
    # A refresh has no user-facing email step; success/failure is reported
    # through `finish_request`, read by the frontend's `useRefreshStatus.ts`.
    notifier = ConsoleNotifier()

    with SupabaseRestUserDirectory(supabase_url, service_role_key) as directory:
        with HttpxActivityTableClient(activity=config.activity) as table_client:
            authenticator = PlaywrightCasAuthenticator(entry_url=config.upv.entry_url)
            verifier = HttpxSessionVerifier(session_check_url=config.upv.session_check_url)
            return refresh_user(
                request_id,
                config,
                directory,
                SealedBoxOpener(private_keys),
                authenticator,
                verifier,
                notifier,
                clock,
                table_client,
                on_credentials_opened=on_credentials_opened,
            )


def _serve(args: argparse.Namespace) -> int:
    """Run the web adapter. Imported lazily: the CLI must work without FastAPI."""
    try:
        import uvicorn

        from upv_auto.adapters.web.api import create_app
    except ImportError:
        logger.error("The web UI needs the extra dependencies: pip install -e \".[web]\"")
        return 1

    static_dir = Path(__file__).resolve().parents[2] / "web" / "dist"
    store = _demo_store() if args.demo else None
    app = create_app(config_path=args.config, store=store, static_dir=static_dir, demo=args.demo)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)
    # Local runs keep secrets in .env; CI provides them as real env vars.
    load_env_file()

    # The server reports config problems over HTTP, so it starts before the
    # config (and its required secrets) are loaded. `seal-keygen`,
    # `book-all`, and `refresh` load config differently from the single-user
    # commands below (no UPV_USERNAME/UPV_PASSWORD; book-all/refresh need
    # Supabase/seal secrets instead), so they are handled in their own
    # functions.
    if args.command == "serve":
        return _serve(args)
    if args.command == "seal-keygen":
        return _seal_keygen(args)
    if args.command == "book-all":
        return _book_all(args)
    if args.command == "refresh":
        return _refresh(args)

    try:
        config = load_config(args.config)
        if getattr(args, "groups", None):
            bookings = [parse_booking_spec(spec) for spec in args.groups]
            config = dataclasses.replace(config, bookings=bookings)
    except ConfigError as exc:
        logger.error(str(exc))
        return 1

    notifier = _build_notifier(config)
    authenticator = PlaywrightCasAuthenticator(entry_url=config.upv.entry_url)
    verifier = HttpxSessionVerifier(session_check_url=config.upv.session_check_url)
    clock = SystemClock(timezone=config.timezone)

    if args.command == "check-login":
        ok = check_login(config.credentials, authenticator, verifier, notifier, clock)
        return 0 if ok else 1

    with HttpxActivityTableClient(activity=config.activity) as table_client:
        if args.command == "list-groups":
            ok = list_groups(config, authenticator, verifier, notifier, clock, table_client)
            return 0 if ok else 1

        if args.command == "book":
            use_case = BookSlotUseCase(
                authenticator=authenticator,
                verifier=verifier,
                table_client=table_client,
                notifier=notifier,
                clock=clock,
                config=config,
            )
            return use_case.execute(skip_wait=args.now)

    return 1  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    sys.exit(main())
