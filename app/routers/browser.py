"""Endpoints exposing browser automation helpers."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.browser import open_webpage
from app.schemas.browser import WebpageOpenRequest, WebpageOpenResponse


router = APIRouter(prefix="/browser", tags=["browser"])


@router.post("/open", response_model=WebpageOpenResponse)
async def open_browser_page(payload: WebpageOpenRequest) -> WebpageOpenResponse:
    """Open the requested page using Playwright and return navigation metadata."""

    result = await open_webpage(str(payload.url), payload.user)
    return WebpageOpenResponse(**result)


__all__ = ["router"]
