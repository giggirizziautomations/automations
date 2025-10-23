"""High-level authentication workflow for Microsoft services."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.core.security import decrypt_str
from app.db import models

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

AUTHENTICATOR_SELECTOR = "[data-automation-id='authenticator-number']"
AUTHENTICATOR_TIMEOUT_MS = 30_000
DEFAULT_TOKEN_TTL = timedelta(minutes=15)


class MicrosoftAuthenticationError(RuntimeError):
    """Raised when the Microsoft authentication workflow fails."""


class BrowserSession(Protocol):
    """Minimal protocol implemented by browser controller handles."""

    page: object

    def close(self) -> None:
        """Close the browser session and release resources."""


class PageHandle(Protocol):
    """Protocol for the subset of Playwright page methods used."""

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> "ElementHandle":
        """Block until the selector resolves to an element."""


class ElementHandle(Protocol):
    """Protocol for the subset of Playwright element methods used."""

    def inner_text(self) -> str:
        """Return the textual content of the element."""


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


def _launch_playwright_session(url: str) -> BrowserSession:
    """Open the supplied URL in a Playwright-controlled browser window."""

    if not _PLAYWRIGHT_AVAILABLE or sync_playwright is None:
        msg = "The playwright package is required to automate the Microsoft login flow"
        raise MicrosoftAuthenticationError(msg)

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
        raise MicrosoftAuthenticationError("Unable to launch Playwright browser") from exc

    return _PlaywrightSession(playwright=playwright, browser=browser, page=page)


def _invoke_power_automate_flow(number: str, email: str, password: str) -> None:
    """Trigger the external Power Automate flow responsible for token creation."""

    settings = get_settings()
    if not settings.power_automate_flow_url:
        raise MicrosoftAuthenticationError(
            "Power Automate flow URL is not configured"
        )

    payload = {"authenticator_number": number, "email": email, "password": password}

    try:
        response = httpx.post(
            settings.power_automate_flow_url,
            json=payload,
            timeout=settings.power_automate_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        msg = "Unable to invoke Power Automate flow"
        raise MicrosoftAuthenticationError(msg) from exc


class MicrosoftAuthenticationService:
    """Orchestrate the automated Microsoft authentication workflow."""

    def __init__(
        self,
        *,
        db: Session,
        browser_launcher: Callable[[str], BrowserSession] | None = None,
        flow_invoker: Callable[[str, str, str], None] | None = None,
        token_ttl: timedelta = DEFAULT_TOKEN_TTL,
        poll_interval: float = 1.0,
        wait_timeout: float = 60.0,
        selector: str = AUTHENTICATOR_SELECTOR,
        selector_timeout_ms: int = AUTHENTICATOR_TIMEOUT_MS,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._db = db
        self._browser_launcher = browser_launcher or _launch_playwright_session
        self._flow_invoker = flow_invoker or _invoke_power_automate_flow
        self._token_ttl = token_ttl
        self._poll_interval = poll_interval
        self._wait_timeout = wait_timeout
        self._selector = selector
        self._selector_timeout_ms = selector_timeout_ms
        self._clock = clock or datetime.utcnow
        self._sleep = sleeper or time.sleep

    def authenticate(self, *, website: str, principal: Principal) -> models.MicrosoftServiceToken:
        """Ensure the user has a fresh Microsoft service token."""

        user = self._resolve_user(principal)

        token = self._get_recent_token(user_id=user.id)
        if token is not None:
            return token

        return self._run_interactive_flow(website=website, user=user)

    def _resolve_user(self, principal: Principal) -> models.User:
        if principal.user_id is None:
            raise MicrosoftAuthenticationError("User authentication context required")

        user = (
            self._db.query(models.User)
            .filter(models.User.id == principal.user_id)
            .first()
        )
        if not user:
            raise MicrosoftAuthenticationError("Authenticated user could not be found")
        if not user.email or not user.password_encrypted:
            raise MicrosoftAuthenticationError(
                "Authenticated user does not have credentials configured"
            )
        return user

    def _get_recent_token(self, *, user_id: int) -> models.MicrosoftServiceToken | None:
        threshold = self._clock() - self._token_ttl
        token = (
            self._db.query(models.MicrosoftServiceToken)
            .filter(models.MicrosoftServiceToken.user_id == user_id)
            .order_by(models.MicrosoftServiceToken.created_at.desc())
            .first()
        )
        if token and token.created_at >= threshold:
            return token
        return None

    def _run_interactive_flow(
        self, *, website: str, user: models.User
    ) -> models.MicrosoftServiceToken:
        session: BrowserSession | None = None
        start_time = self._clock()

        email = user.email
        password = decrypt_str(user.password_encrypted)

        try:
            session = self._browser_launcher(website)
            page = getattr(session, "page", None)
            if page is None:
                raise MicrosoftAuthenticationError(
                    "Playwright session did not expose a page handle"
                )
            code = self._read_authenticator_number(page)
            self._flow_invoker(code, email, password)
        except MicrosoftAuthenticationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            msg = "Microsoft authentication automation failed"
            raise MicrosoftAuthenticationError(msg) from exc
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.debug("Unable to close Playwright session", exc_info=True)

        return self._wait_for_token(user_id=user.id, after=start_time)

    def _read_authenticator_number(self, page: PageHandle) -> str:
        try:
            element = page.wait_for_selector(
                self._selector, timeout=self._selector_timeout_ms
            )
            text = element.inner_text().strip()
        except Exception as exc:
            msg = "Unable to retrieve authenticator number from the page"
            raise MicrosoftAuthenticationError(msg) from exc

        if not text:
            raise MicrosoftAuthenticationError(
                "Authenticator number element returned an empty value"
            )
        return text

    def _wait_for_token(
        self, *, user_id: int, after: datetime
    ) -> models.MicrosoftServiceToken:
        deadline = self._clock() + timedelta(seconds=self._wait_timeout)

        while self._clock() <= deadline:
            self._db.expire_all()
            token = (
                self._db.query(models.MicrosoftServiceToken)
                .filter(models.MicrosoftServiceToken.user_id == user_id)
                .filter(models.MicrosoftServiceToken.created_at >= after)
                .order_by(models.MicrosoftServiceToken.created_at.desc())
                .first()
            )
            if token:
                return token
            self._sleep(self._poll_interval)

        raise MicrosoftAuthenticationError(
            "Timed out waiting for Microsoft service token creation"
        )


__all__ = ["MicrosoftAuthenticationError", "MicrosoftAuthenticationService"]
