"""Example report endpoints protected by scopes."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_scopes


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", dependencies=[Depends(require_scopes(["reports:read"]))])
async def list_reports() -> dict:
    """Return a placeholder list of reports."""

    return {"reports": ["q1", "q2", "q3"]}


__all__ = ["router"]
