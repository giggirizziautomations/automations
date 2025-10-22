"""MSAL device code authentication helpers."""
from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

try:  # pragma: no cover - optional dependency resolution
    from msal import PublicClientApplication, SerializableTokenCache
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    PublicClientApplication = None  # type: ignore[assignment]
    SerializableTokenCache = None  # type: ignore[assignment]
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
        token_cache_path: str | Path | None = None,
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
        self._lock = threading.Lock()
        self._token_cache_path = Path(token_cache_path).expanduser() if token_cache_path else None
        self._cache: SerializableTokenCache | None = None

        if client is not None:
            self._client = client
        else:
            self._client = self._build_client()

    def acquire_token(self) -> Mapping[str, object]:
        """Acquire an access token via the MSAL device code flow with caching."""

        with self._lock:
            cached = self._acquire_token_silent_locked()
            if cached is not None:
                self._persist_cache()
                return cached

            return self._acquire_token_device_flow_locked()

    def acquire_token_silent(self) -> Mapping[str, object] | None:
        """Attempt to acquire a token using the existing MSAL cache only."""

        with self._lock:
            result = self._acquire_token_silent_locked()
            self._persist_cache()
            return result

    def acquire_token_device_flow(self) -> Mapping[str, object]:
        """Run the interactive device code flow regardless of cached tokens."""

        with self._lock:
            return self._acquire_token_device_flow_locked()

    def _build_client(self) -> Any:
        """Create a PublicClientApplication with optional token caching."""

        if not _MSAL_AVAILABLE:
            msg = (
                "The msal package is required to create a client automatically. "
                "Pass an MSAL PublicClientApplication instance explicitly or install msal."
            )
            raise RuntimeError(msg)

        cache = self._load_cache()
        self._cache = cache
        return PublicClientApplication(  # type: ignore[call-arg]
            client_id=self._client_id,
            authority=self._authority,
            token_cache=cache,
        )

    def _load_cache(self) -> SerializableTokenCache | None:
        """Load the token cache from disk if configured."""

        if not _MSAL_AVAILABLE or SerializableTokenCache is None:
            return None
        cache = SerializableTokenCache()
        if not self._token_cache_path:
            return cache

        try:
            if self._token_cache_path.exists():
                cache.deserialize(self._token_cache_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive against corrupt cache
            logger.exception("Unable to deserialize MSAL token cache")
        return cache

    def _persist_cache(self) -> None:
        """Persist the token cache to disk when it has changed."""

        cache = self._cache
        path = self._token_cache_path
        if not cache or not path:
            return

        try:
            if cache.has_state_changed:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(cache.serialize(), encoding="utf-8")
        except Exception:  # pragma: no cover - defensive against filesystem errors
            logger.exception("Unable to persist MSAL token cache")

    def _acquire_token_silent_locked(self) -> Mapping[str, object] | None:
        """Attempt to acquire a token silently using the cache."""

        get_accounts = getattr(self._client, "get_accounts", None)
        acquire_token_silent = getattr(self._client, "acquire_token_silent", None)
        if not callable(get_accounts) or not callable(acquire_token_silent):
            return None

        try:
            accounts: Iterable[Mapping[str, object]] = get_accounts()
        except Exception:  # pragma: no cover - defensive against client errors
            logger.exception("Unable to retrieve accounts for silent MSAL login")
            return None

        for account in accounts:
            try:
                result = acquire_token_silent(list(self._scopes), account=account)
            except Exception:  # pragma: no cover - defensive against client errors
                logger.exception("Silent MSAL token acquisition failed")
                continue

            if isinstance(result, Mapping) and "access_token" in result:
                return result

        return None

    def _acquire_token_device_flow_locked(self) -> Mapping[str, object]:
        """Execute the interactive device flow and persist the cache."""

        flow = self._initiate_flow()
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
            msg = (
                error_description
                or error
                or "Device code flow did not return a token"
            )
            raise DeviceCodeLoginError(msg)

        self._persist_cache()
        return result

    def _initiate_flow(self) -> MutableMapping[str, object]:
        """Start the MSAL device code flow."""

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

        return flow


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
