"""Pydantic schemas for scraping target management."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScrapingTargetCreate(BaseModel):
    """Payload used to create a new scraping target."""

    user_id: int
    site_name: str = Field(..., min_length=1, max_length=150)
    url: str = Field(..., min_length=1, max_length=2048)
    recipe: Optional[str] = Field(default=None, max_length=100)
    parameters: Optional[dict[str, Any]] = None
    notes: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _normalise_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ScrapingTargetOut(BaseModel):
    """Representation of a scraping target returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    site_name: str
    url: str
    recipe: str
    parameters: dict[str, Any]
    notes: str
    has_password: bool


__all__ = ["ScrapingTargetCreate", "ScrapingTargetOut"]
