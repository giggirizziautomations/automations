"""Launch the MSAL device flow in a Playwright-driven browser."""
from __future__ import annotations

import sys
from typing import Mapping

from app.core.config import get_settings
from app.services import DeviceCodeLoginError, DeviceCodeLoginService

try:
    from playwright.sync_api import Error, sync_playwright
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    sync_playwright = None  # type: ignore[assignment]
    Error = Exception  # type: ignore[assignment]


_DEVICE_LOGIN_URL = "https://login.microsoftonline.com/common/oauth2/deviceauth"


def _preview_access_token(token: Mapping[str, object]) -> str:
    """Return a short preview of the MSAL access token for display purposes."""

    value = token.get("access_token")
    if isinstance(value, str) and value:
        return f"{value[:16]}..."
    return "<unavailable>"


def main() -> None:
    """Retrieve a device code and complete the flow using Playwright."""

    if sync_playwright is None:
        print(
            "ERROR: The playwright package is required to run this command.",
            file=sys.stderr,
        )
        sys.exit(1)

    settings = get_settings()

    if not settings.aad_tenant_id:
        print("ERROR: TENANT_ID must be configured in your .env file", file=sys.stderr)
        sys.exit(1)
    if not settings.msal_scopes:
        print("ERROR: SCOPES must be configured in your .env file", file=sys.stderr)
        sys.exit(1)

    try:
        service = DeviceCodeLoginService(
            client_id=settings.msal_client_id,
            authority=settings.msal_authority,
            scopes=settings.msal_scopes,
            open_browser=False,
            token_cache_path=settings.msal_token_cache_path,
        )
    except Exception as exc:  # pragma: no cover - network side-effects
        print(
            f"ERROR: Unable to initialise the device login service: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        flow = service.initiate_device_flow()
    except DeviceCodeLoginError as exc:  # pragma: no cover - network side-effects
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    user_code = flow.get("user_code")
    if not isinstance(user_code, str) or not user_code:
        print("ERROR: The device flow did not return a valid user code", file=sys.stderr)
        sys.exit(1)

    print("Device code retrieved.")
    print("User code:", user_code)
    print()
    print(
        "Opening a Playwright-controlled browser window to pre-fill the code..."
    )

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(_DEVICE_LOGIN_URL, wait_until="load")
        page.fill("input#otc", user_code)
        page.click("input#idSIButton9")
    except Error as exc:  # pragma: no cover - depends on local browser availability
        print(f"ERROR: Unable to drive Playwright browser: {exc}", file=sys.stderr)
        try:
            browser.close()  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            playwright.stop()  # type: ignore[name-defined]
        except Exception:
            pass
        sys.exit(1)

    print()
    print("Complete the sign-in process in the opened browser window.")
    print("Press ENTER here once authentication has finished.")

    try:
        input()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        try:
            browser.close()
        except Exception:
            pass
        playwright.stop()
        sys.exit(1)

    try:
        token = service.acquire_token_with_flow(flow)
    except DeviceCodeLoginError as exc:  # pragma: no cover - network side-effects
        print(f"ERROR: {exc}", file=sys.stderr)
        try:
            browser.close()
        except Exception:
            pass
        playwright.stop()
        sys.exit(1)
    finally:
        try:
            browser.close()
        except Exception:
            pass
        playwright.stop()

    print("Authenticated successfully via device code flow.")
    print("Access token (preview):", _preview_access_token(token))
    if settings.msal_token_cache_path:
        print("Token cache:", settings.msal_token_cache_path)


if __name__ == "__main__":
    main()
