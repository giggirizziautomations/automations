"""Helpers for interacting with web pages via Playwright."""
from __future__ import annotations

import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported for type checkers only
    from playwright.async_api import Playwright


logger = logging.getLogger(__name__)


async def open_webpage(url: str, invoked_by: str) -> dict[str, str]:
    """Open ``url`` in a headed browser on behalf of ``invoked_by``.

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

    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=False)
    except Exception:
        await playwright.stop()
        raise

    page = await browser.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception:
        logger.exception("Failed to open %s for %s", url, invoked_by)
        await browser.close()
        await playwright.stop()
        raise

    logger.info("Successfully opened %s for user %s", url, invoked_by)
    # Intentionally keep the browser session alive so that the page stays open.
    return {"status": "opened", "url": url, "user": invoked_by}


__all__ = ["open_webpage"]
