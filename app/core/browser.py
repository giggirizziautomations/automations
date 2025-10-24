"""Helpers for interacting with web pages via Playwright."""
from __future__ import annotations

import logging
from contextlib import suppress

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported for type checkers only
    from playwright.async_api import Browser, Page, Playwright


logger = logging.getLogger(__name__)


async def open_webpage(url: str, invoked_by: str) -> dict[str, str]:
    """Open ``url`` in a headed browser on behalf of ``invoked_by``.

    The function launches a Chromium instance, navigates to ``url`` and
    determines whether the resulting page is a Microsoft authentication
    endpoint.  When a Microsoft login page is detected, the browser session is
    kept alive for the caller to interact with it.  Otherwise the browser is
    closed immediately and the Playwright resources are released.

    Parameters
    ----------
    url:
        Address of the page to be opened.
    invoked_by:
        Identifier of the user triggering the navigation.

    Returns
    -------
    dict[str, str | bool]
        Metadata about the navigation that can be reused by callers.  The
        ``is_microsoft_login`` key indicates whether a Microsoft login page was
        reached.

    Raises
    ------
    playwright.async_api.Error
        If Playwright encounters an error while launching the browser or
        navigating to the requested page.
    """

    logger.info("Opening %s for user %s", url, invoked_by)

    playwright, browser = await _launch_browser()
    page = await browser.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception:
        logger.exception("Failed to open %s for %s", url, invoked_by)
        await _shutdown_browser(playwright, browser)
        raise

    final_url = page.url
    microsoft_login = _is_microsoft_login_page(page)

    if microsoft_login:
        logger.info(
            "Detected Microsoft login page %s while serving %s", final_url, invoked_by
        )
        # Intentionally keep the browser session alive so that the page stays open.
        return {
            "status": "opened",
            "url": final_url,
            "user": invoked_by,
            "is_microsoft_login": True,
        }

    logger.info("Closing browser because %s is not a Microsoft login page", final_url)
    await _shutdown_browser(playwright, browser)
    return {
        "status": "closed",
        "url": final_url,
        "user": invoked_by,
        "is_microsoft_login": False,
    }


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


def _is_microsoft_login_page(page: Page) -> bool:
    """Return ``True`` if ``page`` represents a Microsoft authentication page."""

    url = page.url.lower()
    return "microsoftonline" in url


__all__ = ["open_webpage"]
