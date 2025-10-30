"""Schemas for browser automation helpers."""
from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field


class WebpageOpenRequest(BaseModel):
    """Payload to request the opening of a webpage."""

    url: AnyHttpUrl = Field(..., description="Address of the page to load")
    session_id: str | None = Field(
        None,
        description=(
            "Identifier of the browser session to use. "
            "When omitted a per-user default session is used."
        ),
        max_length=128,
    )


class WebpageOpenResponse(BaseModel):
    """Response returned after a page has been opened."""

    status: Literal["opened", "closed"] = Field(
        ..., description="Result of the navigation attempt"
    )
    url: AnyHttpUrl = Field(..., description="Address of the page that was opened")
    user: str = Field(
        ..., description="Identifier of the authenticated user who initiated the request"
    )
    session_id: str = Field(
        ..., description="Identifier of the browser session associated with the navigation"
    )


__all__ = ["WebpageOpenRequest", "WebpageOpenResponse"]
