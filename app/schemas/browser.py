"""Schemas for browser automation helpers."""
from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field


class WebpageOpenRequest(BaseModel):
    """Payload to request the opening of a webpage."""

    url: AnyHttpUrl = Field(..., description="Address of the page to load")
    user: str = Field(..., min_length=1, description="Identifier of the user issuing the request")


class WebpageOpenResponse(BaseModel):
    """Response returned after a page has been opened."""

    status: Literal["opened"] = Field("opened", description="Result of the navigation attempt")
    url: AnyHttpUrl = Field(..., description="Address of the page that was opened")
    user: str = Field(..., description="Identifier of the user who initiated the request")


__all__ = ["WebpageOpenRequest", "WebpageOpenResponse"]
