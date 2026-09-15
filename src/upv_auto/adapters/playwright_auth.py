"""Playwright-based CAS authenticator for UPV.

Performs the CAS login with a headless browser and exports the resulting
cookies + user agent as a `Session`, so the fast booking path can replay
that session over plain HTTP (httpx) without needing a browser.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from upv_auto.domain.errors import (
    AuthenticationBlocked,
    AuthenticationFailed,
    AuthenticationUnavailable,
)
from upv_auto.domain.models import Credentials, Session

logger = logging.getLogger(__name__)

DEFAULT_ENTRY_URL = "https://intranet.upv.es/pls/soalu/est_intranet.Ni_portal_n?P_IDIOMA=c"
CAS_HOST = "cas.upv.es"
LOGIN_TIMEOUT_MS = 30_000
ARTIFACTS_DIR = Path("artifacts")

# Defensive: any of these appearing on the login page means we cannot proceed
# safely, so we stop instead of trying to solve or bypass them.
_BLOCKED_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[title*='recaptcha' i]",
    "#captcha",
    "input[name*='otp' i]",
    "input[name*='2fa' i]",
    "input[autocomplete='one-time-code']",
)

# Defensive: several possible containers for CAS's visible error message.
_ERROR_SELECTORS = (".alert", "#msg", ".errors", ".error", "#loginErrorsPanel")


class PlaywrightCasAuthenticator:
    def __init__(self, entry_url: str = DEFAULT_ENTRY_URL, *, headless: bool = True) -> None:
        self._entry_url = entry_url
        self._headless = headless

    def login(self, credentials: Credentials) -> Session:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self._headless)
            try:
                context = browser.new_context()
                page = context.new_page()
                navigation_statuses: list[int] = []
                page.on(
                    "response",
                    lambda response: self._record_navigation(page, response, navigation_statuses),
                )
                try:
                    return self._do_login(page, context, credentials, navigation_statuses)
                except (AuthenticationFailed, AuthenticationBlocked, AuthenticationUnavailable):
                    self._save_screenshot(page)
                    raise
                except PlaywrightError as exc:
                    # Timeouts and network errors (TimeoutError subclasses Error).
                    self._save_screenshot(page)
                    raise AuthenticationUnavailable(f"Browser error during login: {exc}") from exc
            finally:
                browser.close()

    @staticmethod
    def _record_navigation(page: Page, response: Response, statuses: list[int]) -> None:
        if response.request.is_navigation_request() and response.frame == page.main_frame:
            statuses.append(response.status)

    @staticmethod
    def _raise_if_server_error(statuses: list[int], stage: str) -> None:
        if statuses and statuses[-1] >= 500:
            raise AuthenticationUnavailable(f"UPV returned HTTP {statuses[-1]} {stage}")

    def _do_login(
        self, page: Page, context, credentials: Credentials, navigation_statuses: list[int]
    ) -> Session:
        page.goto(self._entry_url)
        self._raise_if_server_error(navigation_statuses, "when opening the login page")
        try:
            page.wait_for_selector("#username", timeout=LOGIN_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise AuthenticationUnavailable("CAS login form did not load") from exc

        self._check_blocked(page)

        page.fill("#username", credentials.username)
        page.fill("#password", credentials.password)
        page.click('button[name="submitBtn"]')

        try:
            page.wait_for_function(
                "() => !location.host.includes('cas.upv.es')",
                timeout=LOGIN_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            self._raise_if_server_error(navigation_statuses, "after submitting credentials")
            self._check_blocked(page)
            error_text = self._read_error_text(page)
            if error_text:
                raise AuthenticationFailed(f"CAS login rejected: {error_text}")
            if page.locator("#password").count() > 0:
                # Form is shown again with no readable error: most likely rejected.
                # Treated as non-retryable so bad credentials never get hammered.
                raise AuthenticationFailed("CAS login did not complete: still on cas.upv.es")
            raise AuthenticationUnavailable("CAS did not respond after submitting credentials")

        page.wait_for_load_state()
        self._raise_if_server_error(navigation_statuses, "after login redirect")

        host = urlparse(page.url).hostname or ""
        if CAS_HOST in host:
            error_text = self._read_error_text(page)
            raise AuthenticationFailed(f"CAS login rejected: {error_text or 'unknown reason'}")

        cookies = context.cookies()
        user_agent = page.evaluate("() => navigator.userAgent")
        return Session(cookies=cookies, user_agent=user_agent)

    def _check_blocked(self, page: Page) -> None:
        for selector in _BLOCKED_SELECTORS:
            if page.locator(selector).count() > 0:
                raise AuthenticationBlocked(
                    f"Unexpected verification step detected ({selector}); refusing to proceed."
                )

    def _read_error_text(self, page: Page) -> str:
        for selector in _ERROR_SELECTORS:
            locator = page.locator(selector)
            if locator.count() > 0:
                text = locator.first.inner_text().strip()
                if text:
                    return text
        return ""

    def _save_screenshot(self, page: Page) -> None:
        try:
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = ARTIFACTS_DIR / f"login-failure-{timestamp}.png"
            page.screenshot(path=str(path))
            logger.info("Saved failure screenshot to %s", path)
        except Exception:  # pragma: no cover - best-effort debugging aid
            logger.exception("Failed to save debug screenshot")
