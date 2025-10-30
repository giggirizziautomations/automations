"""Helpers for interacting with web pages via Playwright."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass

from typing import TYPE_CHECKING, Dict, Tuple

if TYPE_CHECKING:  # pragma: no cover - imported for type checkers only
    from playwright.async_api import Browser, Playwright, Page


logger = logging.getLogger(__name__)


@dataclass
class BrowserSession:
    """Container storing the Playwright runtime, browser and active page."""

    playwright: "Playwright"
    browser: "Browser"
    page: "Page"


class BrowserSessionNotFound(RuntimeError):
    """Raised when a caller attempts to reuse a non-existing session."""

    def __init__(self, user_id: str, session_id: str | None = None) -> None:  # pragma: no cover - trivial
        if session_id is None:
            message = f"No active browser session for user {user_id!r}"
        else:
            message = (
                f"No active browser session for user {user_id!r}"
                f" (session {session_id!r})"
            )
        super().__init__(message)
        self.user_id = user_id
        self.session_id = session_id


_SessionKey = Tuple[str, str]
_DEFAULT_SESSION_ID = "default"
_SESSIONS: Dict[_SessionKey, BrowserSession] = {}


def _session_key(user_id: str, session_id: str | None = None) -> _SessionKey:
    """Return the internal key used to store sessions."""

    resolved_session = session_id or _DEFAULT_SESSION_ID
    return user_id, resolved_session


async def open_webpage(
    url: str,
    invoked_by: str,
    *,
    session_id: str | None = None,
) -> dict[str, str]:
    """Open ``url`` in a headed browser on behalf of ``invoked_by``.

    The function launches a Chromium instance, navigates to ``url`` and waits
    for the page to finish loading before returning.  The browser is kept open
    so that callers can continue interacting with the fully rendered page.
    Any previous session for the same user and session identifier is
    gracefully shut down first.

    Parameters
    ----------
    url:
        Address of the page to be opened.
    invoked_by:
        Identifier of the user triggering the navigation.

    session_id:
        Optional identifier of the browser session to bind to the user. If
        omitted the default session ``"default"`` is used.

    Returns
    -------
    dict[str, str]
        Metadata about the navigation that can be reused by callers.

    Raises
    ------
    playwright.async_api.Error
        If Playwright encounters an error while launching the browser or
        navigating to the requested page.
    """

    logger.info("Opening %s for user %s", url, invoked_by)

    await close_browser_session(invoked_by, session_id=session_id)

    playwright, browser = await _launch_browser()
    page = await browser.new_page()

    try:
        await page.goto(url, wait_until="networkidle")
    except Exception:
        logger.exception("Failed to open %s for %s", url, invoked_by)
        await _shutdown_browser(playwright, browser)
        raise

    final_url = page.url
    session = BrowserSession(playwright=playwright, browser=browser, page=page)
    key = _session_key(invoked_by, session_id)
    _SESSIONS[key] = session
    _register_session_cleanup(key, session)
    logger.info("Leaving browser open at %s for %s", final_url, invoked_by)
    resolved_session = key[1]
    return {
        "status": "opened",
        "url": final_url,
        "user": invoked_by,
        "session_id": resolved_session,
    }


def get_active_session(user_id: str, session_id: str | None = None) -> BrowserSession:
    """Return the active browser session for ``user_id``.

    Raises
    ------
    BrowserSessionNotFound
        If the user has not previously opened a browser session.
    """

    key = _session_key(user_id, session_id)
    try:
        return _SESSIONS[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise BrowserSessionNotFound(user_id, key[1]) from exc


def get_active_page(user_id: str, session_id: str | None = None) -> "Page":
    """Return the Playwright page associated with ``user_id``."""

    return get_active_session(user_id, session_id=session_id).page


async def close_browser_session(user_id: str, session_id: str | None = None) -> None:
    """Close and remove any active browser session for ``user_id``."""

    key = _session_key(user_id, session_id)
    session = _SESSIONS.pop(key, None)
    if not session:
        return
    await _shutdown_browser(session.playwright, session.browser)


def _register_session_cleanup(session_key: _SessionKey, session: BrowserSession) -> None:
    """Ensure ``session`` is cleaned up when the browser or page is closed."""

    cleanup_started = False
    user_id, session_id = session_key

    async def _cleanup() -> None:
        logger.info(
            "Cleaning up browser session for %s (session %s)",
            user_id,
            session_id,
        )
        _SESSIONS.pop(session_key, None)
        await _shutdown_browser(session.playwright, session.browser)

    def _schedule_cleanup() -> None:
        nonlocal cleanup_started
        if cleanup_started:
            return
        cleanup_started = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Unable to schedule cleanup for %s: no running loop", user_id)
            return
        loop.create_task(_cleanup())

    session.browser.on("disconnected", _schedule_cleanup)
    session.page.on("close", _schedule_cleanup)


async def _launch_browser(*, headless: bool = False) -> tuple[Playwright, Browser]:
    """Start Playwright and launch a Chromium browser instance."""

    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=headless)
    except Exception:
        await playwright.stop()
        raise
    return playwright, browser


async def _shutdown_browser(playwright: Playwright, browser: Browser) -> None:
    """Gracefully close the browser and stop Playwright."""

    with suppress(Exception):
        await browser.close()
    with suppress(Exception):
        await playwright.stop()


__all__ = [
    "BrowserSession",
    "BrowserSessionNotFound",
    "open_webpage",
    "get_active_session",
    "get_active_page",
    "close_browser_session",
]
