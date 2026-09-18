"""Command-line entry point.

Usage:
    python -m upv_auto check-login [--config PATH]
    python -m upv_auto list-groups [--config PATH]
    python -m upv_auto book [--config PATH] [--now]
    python -m upv_auto serve [--config PATH] [--host HOST] [--port PORT]

--now skips waiting for the booking window to open; useful for local testing.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
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
    # config (and its required secrets) are loaded.
    if args.command == "serve":
        return _serve(args)

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
