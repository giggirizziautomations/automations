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


class ScrapingActionStep(BaseModel):
    """Structure describing a single scraping step to be persisted."""

    model_config = ConfigDict(extra="allow")

    action: str = Field(..., min_length=1)


class ScrapingActionsUpdate(BaseModel):
    """Payload used to update the actions associated with a scraping target."""

    actions: list[ScrapingActionStep]
    parameters: Optional[dict[str, Any]] = None

    @field_validator("actions")
    @classmethod
    def _ensure_actions(cls, value: list[ScrapingActionStep]) -> list[ScrapingActionStep]:
        if not value:
            raise ValueError("actions must contain at least one entry")
        return value


class ScrapingActionSuggestion(BaseModel):
    """Payload describing an HTML snippet to convert into a scraping action."""

    html: str = Field(..., min_length=1)
    suggestion: str = Field(..., min_length=1)
    value: Optional[str] = None
    settle_ms: Optional[int] = Field(default=None, ge=0)


class ScrapingActionDocument(BaseModel):
    """JSON structure returned when rendering scraping actions from HTML."""

    actions: list[ScrapingActionStep]
    settle_ms: Optional[int] = Field(default=None, ge=0)


__all__ = [
    "ScrapingActionStep",
    "ScrapingActionsUpdate",
    "ScrapingActionDocument",
    "ScrapingActionSuggestion",
    "ScrapingTargetCreate",
    "ScrapingTargetOut",
]
