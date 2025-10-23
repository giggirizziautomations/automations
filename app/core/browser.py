"""Helpers for interacting with web pages via Playwright."""
from __future__ import annotations

import logging

from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)


async def open_webpage(url: str, invoked_by: str) -> dict[str, str]:
    """Open ``url`` in a headless browser on behalf of ``invoked_by``.

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

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception:
            logger.exception("Failed to open %s for %s", url, invoked_by)
            raise
        finally:
            await browser.close()

    logger.info("Successfully opened %s for user %s", url, invoked_by)

    return {"status": "opened", "url": url, "user": invoked_by}


__all__ = ["open_webpage"]
