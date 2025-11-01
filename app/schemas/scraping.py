"""Pydantic models for scraping automation endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class ScrapingAction(BaseModel):
    """Structured instruction that can be executed by the scraper."""

    type: Literal["click", "fill", "select", "wait", "custom"]
    selector: str
    description: str
    target_tag: str | None = None
    input_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ScrapingActionPreviewRequest(BaseModel):
    """Natural language request used to generate an automation action."""

    instruction: str = Field(..., min_length=1)
    html_snippet: str = Field(..., min_length=1)
    store_text_as: str | None = Field(default=None, min_length=1)


class ScrapingRoutineCreateRequest(BaseModel):
    """Payload used to create a scraping routine."""

    url: HttpUrl
    mode: Literal["headless", "headed"] = "headless"
    actions: list[ScrapingAction] = Field(default_factory=list)
    email: EmailStr | None = None
    password: str | None = None


class ScrapingRoutineResponse(BaseModel):
    """Representation of a persisted scraping routine."""

    id: int
    url: HttpUrl
    mode: Literal["headless", "headed"]
    actions: list[ScrapingAction] = Field(default_factory=list)
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)


class ScrapingActionMutationRequest(BaseModel):
    """Payload for appending or replacing an action on a routine."""

    instruction: str = Field(..., min_length=1)
    html_snippet: str = Field(..., min_length=1)
    store_text_as: str | None = Field(default=None, min_length=1)


class ScrapingStepResult(BaseModel):
    """Result of executing a single scraping action."""

    index: int
    type: Literal["click", "fill", "select", "wait", "custom"]
    selector: str
    status: Literal["success", "error", "skipped"]
    detail: str | None = None
    input_text: str | None = None
    captured_text: str | None = None


class ScrapingExecutionResponse(BaseModel):
    """Response returned after executing a scraping routine."""

    routine_id: int
    url: HttpUrl
    results: list[ScrapingStepResult] = Field(default_factory=list)


__all__ = [
    "ScrapingAction",
    "ScrapingActionPreviewRequest",
    "ScrapingRoutineCreateRequest",
    "ScrapingRoutineResponse",
    "ScrapingActionMutationRequest",
    "ScrapingStepResult",
    "ScrapingExecutionResponse",
]
