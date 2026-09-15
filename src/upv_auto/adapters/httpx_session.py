"""httpx adapters: build an authenticated client from a Session, and verify sessions."""

from __future__ import annotations

import httpx

from upv_auto.domain.models import Session

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def build_client(session: Session, *, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.Client:
    """Build an httpx.Client carrying the cookies and user agent from a login Session."""
    client = httpx.Client(
        headers={"User-Agent": session.user_agent},
        timeout=timeout,
        follow_redirects=True,
    )
    for cookie in session.cookies:
        client.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain") or "",
            path=cookie.get("path") or "/",
        )
    return client


class HttpxSessionVerifier:
    """Checks that a session is still authenticated by hitting a known UPV page."""

    def __init__(self, session_check_url: str, *, cas_host: str = "cas.upv.es") -> None:
        self._session_check_url = session_check_url
        self._cas_host = cas_host

    def is_valid(self, session: Session) -> bool:
        with build_client(session) as client:
            try:
                response = client.get(self._session_check_url)
            except httpx.HTTPError:
                return False

        if response.status_code >= 400:
            return False
        return httpx.URL(str(response.url)).host != self._cas_host
