"""MSAL device code authentication helpers."""
from __future__ import annotations

import logging
import webbrowser
from typing import Any, Callable, Mapping, MutableMapping, Sequence

try:  # pragma: no cover - optional dependency resolution
    from msal import PublicClientApplication
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    PublicClientApplication = None  # type: ignore[assignment]
    _MSAL_AVAILABLE = False
else:  # pragma: no cover - exercised when msal is installed
    _MSAL_AVAILABLE = True


logger = logging.getLogger(__name__)


class DeviceCodeLoginError(RuntimeError):
    """Raised when the device code flow fails to return an access token."""


class DeviceCodeLoginService:
    """Perform a device code authentication flow using MSAL."""

    def __init__(
        self,
        *,
        client_id: str,
        authority: str,
        scopes: Sequence[str],
        open_browser: bool = True,
        client: Any | None = None,
        browser_opener: Callable[[str], object] | None = None,
    ) -> None:
        if not client_id:
            msg = "An MSAL client ID is required to perform the device code flow"
            raise ValueError(msg)
        if not scopes:
            msg = "At least one scope must be supplied for the device code flow"
            raise ValueError(msg)

        self._client_id = client_id
        self._authority = authority
        self._scopes = tuple(scopes)
        self._open_browser = open_browser
        self._browser_opener = browser_opener or webbrowser.open
        if client is not None:
            self._client = client
        else:
            if not _MSAL_AVAILABLE:
                msg = (
                    "The msal package is required to create a client automatically. "
                    "Pass an MSAL PublicClientApplication instance explicitly or install msal."
                )
                raise RuntimeError(msg)

            self._client = PublicClientApplication(  # type: ignore[call-arg]
                client_id=self._client_id,
                authority=self._authority,
            )

    def acquire_token(self) -> Mapping[str, object]:
        """Acquire an access token via the MSAL device code flow."""

        try:
            flow: MutableMapping[str, object] = self._client.initiate_device_flow(
                scopes=list(self._scopes)
            )
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Unable to initiate the device code flow"
            raise DeviceCodeLoginError(msg) from exc

        if "user_code" not in flow:
            error_description = flow.get("error_description")
            msg = error_description or "Failed to initiate the device code flow"
            raise DeviceCodeLoginError(msg)

        verification_url = _build_verification_url(flow)
        if self._open_browser and verification_url:
            try:
                self._browser_opener(verification_url)
            except Exception:  # pragma: no cover - platform dependent
                logger.exception("Unable to open browser for device code login")

        result = self._client.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            error_description = result.get("error_description")
            error = result.get("error")
            msg = error_description or error or "Device code flow did not return a token"
            raise DeviceCodeLoginError(msg)

        return result


def _build_verification_url(flow: Mapping[str, object]) -> str | None:
    """Derive the verification URL to open in the user's browser."""

    verification_complete = flow.get("verification_uri_complete")
    if isinstance(verification_complete, str) and verification_complete:
        return verification_complete

    verification_uri = flow.get("verification_uri")
    user_code = flow.get("user_code")
    if isinstance(verification_uri, str) and isinstance(user_code, str):
        return f"{verification_uri}?code={user_code}"

    return None


__all__ = ["DeviceCodeLoginError", "DeviceCodeLoginService"]
