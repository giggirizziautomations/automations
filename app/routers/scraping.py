"""Endpoints to manage scraping target configurations."""
from __future__ import annotations

import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_admin
from app.db import models
from app.db.base import get_db
from app.schemas.scraping import (
    ScrapingActionDocument,
    ScrapingActionsUpdate,
    ScrapingActionSuggestion,
    ScrapingTargetCreate,
    ScrapingTargetOut,
)
from app.scraping.helpers import build_action_step, build_actions_document


router = APIRouter(prefix="/scraping-targets", tags=["scraping"])


def _serialize_target(target: models.ScrapingTarget) -> ScrapingTargetOut:
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

    return _serialize_target(target)


@router.put("/{target_id}/actions", response_model=ScrapingTargetOut)
async def update_scraping_target_actions(
    target_id: int,
    payload: ScrapingActionsUpdate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Replace the JSON actions document stored for ``target_id``."""

    target = (
        db.query(models.ScrapingTarget)
        .filter(models.ScrapingTarget.id == target_id)
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraping target not found",
        )

    current_parameters = json.loads(target.parameters or "{}")
    if payload.parameters:
        current_parameters.update(payload.parameters)

    current_parameters["actions"] = [
        step.model_dump(exclude_none=True) for step in payload.actions
    ]

    target.parameters = json.dumps(current_parameters)
    db.add(target)
    db.commit()
    db.refresh(target)

    return _serialize_target(target)


@router.post("/actions/preview", response_model=ScrapingActionDocument)
async def preview_scraping_action(
    payload: ScrapingActionSuggestion,
    _: Principal = Depends(require_admin),
) -> ScrapingActionDocument:
    """Render a scraping action document from the provided HTML snippet."""

    document = build_actions_document(
        payload.html,
        payload.suggestion,
        value=payload.value,
        settle_ms=payload.settle_ms,
    )
    return ScrapingActionDocument(**document)


@router.post("/{target_id}/actions/from-html", response_model=ScrapingTargetOut)
async def append_scraping_action_from_html(
    target_id: int,
    payload: ScrapingActionSuggestion,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Append a generated scraping action to the stored configuration."""

    target = (
        db.query(models.ScrapingTarget)
        .filter(models.ScrapingTarget.id == target_id)
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraping target not found",
        )

    current_parameters = json.loads(target.parameters or "{}")
    actions: list[dict[str, object]] = []
    existing_actions = current_parameters.get("actions")
    if isinstance(existing_actions, list):
        actions.extend(
            step
            for step in existing_actions
            if isinstance(step, dict)
        )

    new_action = build_action_step(
        payload.html,
        payload.suggestion,
        value=payload.value,
    )
    actions.append(new_action)
    current_parameters["actions"] = actions

    if payload.settle_ms is not None:
        current_parameters["settle_ms"] = payload.settle_ms

    target.parameters = json.dumps(current_parameters)
    db.add(target)
    db.commit()
    db.refresh(target)

    return _serialize_target(target)


__all__ = ["router"]
