"""Automate MSAL device login using Playwright."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Protocol

from .msal_device import DeviceCodeLoginError, DeviceCodeLoginService, _build_verification_url

try:  # pragma: no cover - optional dependency resolution
    from playwright.sync_api import Browser, Page, Playwright, sync_playwright
except ModuleNotFoundError:  # pragma: no cover - optional dependency resolution
    sync_playwright = None  # type: ignore[assignment]
    Playwright = None  # type: ignore[assignment]
    Browser = None  # type: ignore[assignment]
    Page = None  # type: ignore[assignment]
    _PLAYWRIGHT_AVAILABLE = False
else:  # pragma: no cover - exercised when playwright is installed
    _PLAYWRIGHT_AVAILABLE = True


logger = logging.getLogger(__name__)


class BrowserSession(Protocol):
    """Minimal protocol implemented by browser controller handles."""

    def close(self) -> None:
        """Close the browser session and release resources."""


@dataclass
class _PlaywrightSession:
    """Owns the Playwright lifecycle for the automation run."""

    playwright: Playwright
    browser: Browser
    page: Page

    def close(self) -> None:  # pragma: no cover - depends on playwright availability
        try:
            self.page.close()
        except Exception:
            logger.debug("Unable to close Playwright page", exc_info=True)
        try:
            self.browser.close()
        except Exception:
            logger.debug("Unable to close Playwright browser", exc_info=True)
        try:
            self.playwright.stop()
        except Exception:
            logger.debug("Unable to stop Playwright runtime", exc_info=True)


def _launch_playwright_browser(url: str) -> BrowserSession:
    """Open the verification URL in a Playwright-controlled browser window."""

    if not _PLAYWRIGHT_AVAILABLE or sync_playwright is None:
        msg = "The playwright package is required to automate the device login flow"
        raise DeviceCodeLoginError(msg)

    try:  # pragma: no cover - network/UI side-effects
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="load")
    except Exception as exc:  # pragma: no cover - depends on local browser availability
        try:
            playwright.stop()  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - best effort cleanup
            logger.debug("Unable to stop Playwright after launch failure", exc_info=True)
        raise DeviceCodeLoginError("Unable to launch Playwright browser") from exc

    return _PlaywrightSession(playwright=playwright, browser=browser, page=page)


class PlaywrightDeviceLoginAutomation:
    """Complete the device login flow by driving a Playwright browser."""

    def __init__(
        self,
        *,
        service: DeviceCodeLoginService,
        browser_launcher: Callable[[str], BrowserSession] | None = None,
    ) -> None:
        self._service = service
        self._browser_launcher = browser_launcher or _launch_playwright_browser

    def authenticate(self) -> dict[str, object]:
        """Run the Playwright-assisted device login flow and return the token."""

        flow = self._service.initiate_device_flow()
        verification_url = _build_verification_url(flow)
        if not verification_url:
            msg = "Device code flow did not include a verification URL"
            raise DeviceCodeLoginError(msg)

        controller: BrowserSession | None = None

        try:
            controller = self._browser_launcher(verification_url)
        except DeviceCodeLoginError:
            raise
        except Exception as exc:
            msg = "Unable to open browser for device login"
            raise DeviceCodeLoginError(msg) from exc

        try:
            token = self._service.acquire_token_with_flow(flow)
        finally:
            if controller:
                try:
                    controller.close()
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.debug("Unable to close Playwright session", exc_info=True)

        return dict(token)


__all__ = ["PlaywrightDeviceLoginAutomation", "BrowserSession"]
