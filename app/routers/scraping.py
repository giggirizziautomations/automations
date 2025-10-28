"""Endpoints supporting the scraping instruction workflow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.scraping import generate_scraping_action
from app.core.security import decrypt_str, encrypt_str
from app.db import models
from app.db.base import get_db
from app.schemas.scraping import (
    ScrapingAction,
    ScrapingActionMutationRequest,
    ScrapingActionPreviewRequest,
    ScrapingRoutineCreateRequest,
    ScrapingRoutineResponse,
)


router = APIRouter(prefix="/scraping", tags=["scraping"])


def _serialise_routine(routine: models.ScrapingRoutine) -> ScrapingRoutineResponse:
    actions = [ScrapingAction(**item) for item in routine.get_actions()]
    password_plain = decrypt_str(routine.password_encrypted)
    return ScrapingRoutineResponse(
        id=routine.id,
        url=routine.url,
        mode=routine.mode,
        actions=actions,
        email=routine.email,
        password=password_plain,
    )


def _get_owned_routine(
    *,
    db: Session,
    routine_id: int,
    user: models.User,
) -> models.ScrapingRoutine:
    routine = (
        db.query(models.ScrapingRoutine)
        .filter(
            models.ScrapingRoutine.id == routine_id,
            models.ScrapingRoutine.user_id == user.id,
        )
        .first()
    )
    if not routine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routine not found")
    return routine


def _generate_action(payload: ScrapingActionPreviewRequest) -> ScrapingAction:
    raw_action = generate_scraping_action(payload.instruction, payload.html_snippet)
    return ScrapingAction(**raw_action)


@router.post(
    "/routines",
    response_model=ScrapingRoutineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scraping_routine(
    payload: ScrapingRoutineCreateRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingRoutineResponse:
    """Create a new scraping routine owned by the authenticated user."""

    email = payload.email or user.email
    password = payload.password
    if password is None:
        password = decrypt_str(user.password_encrypted)

    actions = [action.model_dump() for action in payload.actions]
    routine = models.ScrapingRoutine(
        user_id=user.id,
        url=str(payload.url),
        mode=payload.mode,
        email=email,
        password_encrypted=encrypt_str(password),
        actions=actions,
    )
    db.add(routine)
    db.commit()
    db.refresh(routine)
    return _serialise_routine(routine)


@router.post(
    "/actions/preview",
    response_model=ScrapingAction,
)
def preview_scraping_action(
    payload: ScrapingActionPreviewRequest,
    user: models.User = Depends(get_current_user),
) -> ScrapingAction:
    """Return the structured representation of the requested action."""

    return _generate_action(payload)


@router.post(
    "/routines/{routine_id}/actions",
    response_model=ScrapingRoutineResponse,
)
def append_scraping_action(
    routine_id: int,
    payload: ScrapingActionMutationRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingRoutineResponse:
    """Append a new action to an existing routine."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    action_payload = ScrapingActionPreviewRequest(
        instruction=payload.instruction,
        html_snippet=payload.html_snippet,
    )
    action = _generate_action(action_payload)

    actions = routine.get_actions()
    actions.append(action.model_dump())
    routine.set_actions(actions)

    db.add(routine)
    db.commit()
    db.refresh(routine)
    return _serialise_routine(routine)


@router.patch(
    "/routines/{routine_id}/actions/{action_index}",
    response_model=ScrapingRoutineResponse,
)
def patch_scraping_action(
    routine_id: int,
    action_index: int,
    payload: ScrapingActionMutationRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingRoutineResponse:
    """Replace an action in a routine using new natural language instructions."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    actions = routine.get_actions()
    if action_index < 0 or action_index >= len(actions):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    action_payload = ScrapingActionPreviewRequest(
        instruction=payload.instruction,
        html_snippet=payload.html_snippet,
    )
    action = _generate_action(action_payload)
    actions[action_index] = action.model_dump()
    routine.set_actions(actions)

    db.add(routine)
    db.commit()
    db.refresh(routine)
    return _serialise_routine(routine)


__all__ = ["router"]
