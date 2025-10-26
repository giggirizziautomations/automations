"""Endpoints to manage scraping target configurations."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_admin
from app.db import models
from app.db.base import get_db
from app.schemas.scraping import ScrapingTargetCreate, ScrapingTargetOut


router = APIRouter(prefix="/scraping-targets", tags=["scraping"])


@router.post("", response_model=ScrapingTargetOut, status_code=status.HTTP_201_CREATED)
async def create_scraping_target(
    payload: ScrapingTargetCreate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Create a scraping target for the specified user."""

    existing = (
        db.query(models.ScrapingTarget)
        .filter(
            models.ScrapingTarget.user_id == payload.user_id,
            models.ScrapingTarget.site_name == payload.site_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scraping target already exists for this user and site",
        )

    parameters_json = json.dumps(payload.parameters or {})
    notes_value = (payload.notes or "").strip()

    target = models.ScrapingTarget(
        user_id=payload.user_id,
        site_name=payload.site_name,
        url=payload.url,
        recipe=(payload.recipe or "default").strip() or "default",
        parameters=parameters_json,
        notes=notes_value,
    )
    target.set_password(payload.password)

    db.add(target)
    db.commit()
    db.refresh(target)

    return ScrapingTargetOut(
        id=target.id,
        user_id=target.user_id,
        site_name=target.site_name,
        url=target.url,
        recipe=target.recipe,
        parameters=json.loads(target.parameters or "{}"),
        notes=target.notes,
        has_password=bool(target.password_encrypted),
    )


__all__ = ["router"]
