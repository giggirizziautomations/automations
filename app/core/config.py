"""Application configuration management."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


DEFAULT_PUBLIC_CLIENT_ID = "04f0c124-f2bc-4f59-9a70-39b0f486b5ab"
DEFAULT_COMMON_AUTHORITY = "https://login.microsoftonline.com/common"
DEFAULT_DEVICE_SCOPES = (
    "https://yourorg.crm.dynamics.com/user_impersonation",
    "offline_access",
    "openid",
    "profile",
)


class Settings(BaseModel):
    """Runtime configuration values loaded from the environment."""

    app_name: str = Field(default="Automations API")
    database_url: str = Field(default="sqlite:///./app.db")
    fernet_key: Optional[str] = None
    jwt_secret: Optional[str] = None
    access_token_expire_minutes: int = Field(default=15, ge=1)
    log_level: str = Field(default="INFO")
    aad_tenant_id: Optional[str] = None
    msal_client_id: str = Field(default=DEFAULT_PUBLIC_CLIENT_ID)
    msal_authority: str = Field(default=DEFAULT_COMMON_AUTHORITY)
    msal_scopes: tuple[str, ...] = Field(default=DEFAULT_DEVICE_SCOPES)
    msal_open_browser: bool = Field(default=True)
    msal_token_cache_path: Optional[str] = Field(
        default="./data/aad_user_token_cache.json"
    )

    class Config:
        frozen = True


def _build_settings() -> Settings:
    """Construct settings object from environment variables."""

    tenant_id = _get_env("TENANT_ID")
    authority = _derive_authority(tenant_id)
    raw_scopes = _get_scopes()

    return Settings(
        app_name=os.getenv("APP_NAME", "Automations API"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
        fernet_key=os.getenv("FERNET_KEY"),
        jwt_secret=os.getenv("JWT_SECRET"),
        access_token_expire_minutes=int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        aad_tenant_id=tenant_id,
        msal_client_id=_resolve_client_id(),
        msal_authority=authority,
        msal_scopes=raw_scopes,
        msal_open_browser=_parse_bool(os.getenv("MSAL_OPEN_BROWSER", "true")),
        msal_token_cache_path=_resolve_cache_path(),
    )


def _get_env(name: str) -> Optional[str]:
    """Read an environment variable stripping whitespace and empty values."""

    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_client_id() -> str:
    """Determine which client ID should be used for MSAL device code flows."""

    client_id = _get_env("MSAL_CLIENT_ID")
    if client_id:
        return client_id
    public_client_id = _get_env("PUBLIC_CLIENT_ID")
    if public_client_id:
        return public_client_id
    return DEFAULT_PUBLIC_CLIENT_ID


def _resolve_cache_path() -> Optional[str]:
    """Resolve the configured token cache path supporting legacy variables."""

    legacy = _get_env("MSAL_TOKEN_CACHE_PATH")
    if legacy:
        return legacy
    return _get_env("TOKEN_CACHE_PATH") or "./data/aad_user_token_cache.json"


def _derive_authority(tenant_id: Optional[str]) -> str:
    """Compute the Azure AD authority based on tenant or legacy settings."""

    if tenant_id:
        return f"https://login.microsoftonline.com/{tenant_id}"
    legacy_authority = _get_env("MSAL_AUTHORITY")
    if legacy_authority:
        return legacy_authority
    return DEFAULT_COMMON_AUTHORITY


def _get_scopes() -> tuple[str, ...]:
    """Resolve scope configuration supporting both new and legacy formats."""

    raw_scopes = _get_env("SCOPES")
    if raw_scopes:
        return _parse_space(raw_scopes)
    legacy_scopes = _get_env("MSAL_SCOPES")
    if legacy_scopes:
        return _parse_csv(legacy_scopes)
    return DEFAULT_DEVICE_SCOPES


def _parse_csv(raw_value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated string into a tuple of scopes."""

    if not raw_value:
        return tuple()
    scopes = [scope.strip() for scope in raw_value.split(",") if scope.strip()]
    return tuple(scopes)


def _parse_space(raw_value: str) -> tuple[str, ...]:
    """Parse a whitespace-separated string of scopes."""

    return tuple(scope for scope in raw_value.split() if scope)


def _parse_bool(raw_value: str | None) -> bool:
    """Convert a string environment flag into a boolean."""

    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    load_dotenv(override=False)
    return _build_settings()


def reload_settings() -> Settings:
    """Clear the settings cache and rebuild the configuration."""

    get_settings.cache_clear()  # type: ignore[attr-defined]
    return get_settings()


__all__ = ["Settings", "get_settings", "reload_settings"]
