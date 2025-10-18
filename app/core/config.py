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
    )


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
