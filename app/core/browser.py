"""Helpers for interacting with web pages via Playwright."""
from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass

from typing import TYPE_CHECKING, Dict

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

    def __init__(self, user_id: str) -> None:  # pragma: no cover - trivial
        super().__init__(f"No active browser session for user {user_id!r}")
        self.user_id = user_id


_SESSIONS: Dict[str, BrowserSession] = {}


async def open_webpage(url: str, invoked_by: str) -> dict[str, str]:
    """Open ``url`` in a headed browser on behalf of ``invoked_by``.

    The function launches a Chromium instance, navigates to ``url`` and waits
    for the page to finish loading before returning.  The browser is kept open
    so that callers can continue interacting with the fully rendered page.
    Any previous session for the same user is gracefully shut down first.

    Parameters
    ----------
    url:
        Address of the page to be opened.
    invoked_by:
        Identifier of the user triggering the navigation.

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

    await close_browser_session(invoked_by)

    playwright, browser = await _launch_browser()
    page = await browser.new_page()

    try:
        await page.goto(url, wait_until="networkidle")
    except Exception:
        logger.exception("Failed to open %s for %s", url, invoked_by)
        await _shutdown_browser(playwright, browser)
        raise

    final_url = page.url
    _SESSIONS[invoked_by] = BrowserSession(playwright=playwright, browser=browser, page=page)
    logger.info("Leaving browser open at %s for %s", final_url, invoked_by)
    return {
        "status": "opened",
        "url": final_url,
        "user": invoked_by,
    }


def get_active_session(user_id: str) -> BrowserSession:
    """Return the active browser session for ``user_id``.

    Raises
    ------
    BrowserSessionNotFound
        If the user has not previously opened a browser session.
    """

    try:
        return _SESSIONS[user_id]
    except KeyError as exc:  # pragma: no cover - defensive
        raise BrowserSessionNotFound(user_id) from exc


def get_active_page(user_id: str) -> "Page":
    """Return the Playwright page associated with ``user_id``."""

    return get_active_session(user_id).page


async def close_browser_session(user_id: str) -> None:
    """Close and remove any active browser session for ``user_id``."""

    session = _SESSIONS.pop(user_id, None)
    if not session:
        return
    await _shutdown_browser(session.playwright, session.browser)


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
