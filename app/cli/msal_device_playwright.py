"""Launch the MSAL device flow in a Playwright-driven browser."""
from __future__ import annotations

import sys
from typing import Mapping

from app.core.config import get_settings
from app.services import (
    DeviceCodeLoginError,
    DeviceCodeLoginService,
    PlaywrightDeviceLoginAutomation,
)


def _preview_access_token(token: Mapping[str, object]) -> str:
    """Return a short preview of the MSAL access token for display purposes."""

    value = token.get("access_token")
    if isinstance(value, str) and value:
        return f"{value[:16]}..."
    return "<unavailable>"


def main() -> None:
    """Retrieve a device code and complete the flow using Playwright."""

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

    automation = PlaywrightDeviceLoginAutomation(service=service)

    print("Opening a Playwright-controlled browser to complete the device code flow...")

    try:
        token = automation.authenticate()
    except DeviceCodeLoginError as exc:  # pragma: no cover - network side-effects
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Authenticated successfully via device code flow.")
    print("Access token (preview):", _preview_access_token(token))
    if settings.msal_token_cache_path:
        print("Token cache:", settings.msal_token_cache_path)


if __name__ == "__main__":
    main()
