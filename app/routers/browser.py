"""Endpoints exposing browser automation helpers."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.browser import open_webpage
from app.db import models
from app.schemas.browser import WebpageOpenRequest, WebpageOpenResponse


router = APIRouter(prefix="/browser", tags=["browser"])


@router.post("/open", response_model=WebpageOpenResponse)
async def open_browser_page(
    payload: WebpageOpenRequest,
    user: models.User = Depends(get_current_user),
) -> WebpageOpenResponse:
    """Open the requested page using Playwright and return navigation metadata."""

    result = await open_webpage(
        str(payload.url),
        str(user.id),
        session_id=payload.session_id,
    )
    return WebpageOpenResponse(**result)


__all__ = ["router"]
