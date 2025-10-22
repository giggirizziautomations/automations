"""Application configuration management."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class Settings(BaseModel):
    """Runtime configuration values loaded from the environment."""

    app_name: str = Field(default="Automations API")
    database_url: str = Field(default="sqlite:///./app.db")
    fernet_key: Optional[str] = None
    jwt_secret: Optional[str] = None
    access_token_expire_minutes: int = Field(default=15, ge=1)
    log_level: str = Field(default="INFO")
    msal_client_id: Optional[str] = None
    msal_authority: str = Field(
        default="https://login.microsoftonline.com/common"
    )
    msal_scopes: tuple[str, ...] = Field(
        default=("https://analysis.windows.net/powerbi/api/.default",)
    )
    msal_open_browser: bool = Field(default=True)

    class Config:
        frozen = True


def _build_settings() -> Settings:
    """Construct settings object from environment variables."""

    return Settings(
        app_name=os.getenv("APP_NAME", "Automations API"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
        fernet_key=os.getenv("FERNET_KEY"),
        jwt_secret=os.getenv("JWT_SECRET"),
        access_token_expire_minutes=int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        msal_client_id=os.getenv("MSAL_CLIENT_ID"),
        msal_authority=os.getenv(
            "MSAL_AUTHORITY", "https://login.microsoftonline.com/common"
        ),
        msal_scopes=_parse_csv(
            os.getenv(
                "MSAL_SCOPES",
                "https://analysis.windows.net/powerbi/api/.default",
            )
        ),
        msal_open_browser=_parse_bool(os.getenv("MSAL_OPEN_BROWSER", "true")),
    )


def _parse_csv(raw_value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated string into a tuple of scopes."""

    if not raw_value:
        return tuple()
    scopes = [scope.strip() for scope in raw_value.split(",") if scope.strip()]
    return tuple(scopes)


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
