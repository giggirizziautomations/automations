"""Endpoints supporting the scraping instruction workflow."""
from __future__ import annotations

import json
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.browser import BrowserSessionNotFound, get_active_page, open_webpage
from app.core.json_utils import relaxed_json_loads
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
    ScrapingExecutionResponse,
)
from app.services.scraping_executor import (
    RoutineCredentials,
    execute_scraping_routine as execute_scraping_routine_service,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


router = APIRouter(prefix="/scraping", tags=["scraping"])


PREVIEW_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": ScrapingActionPreviewRequest.model_json_schema(),
        }
    },
}

MUTATION_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": ScrapingActionMutationRequest.model_json_schema(),
        }
    },
}


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


async def _parse_relaxed_payload(
    request: Request, model: type[ModelT]
) -> ModelT:
    """Decode the request body using the relaxed JSON loader and validate it."""

    try:
        raw_body = await request.body()
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Unable to read request body"
        ) from exc
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid UTF-8",
        ) from exc
    try:
        data = relaxed_json_loads(body_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="JSON body must be an object",
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


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
    openapi_extra={"requestBody": PREVIEW_REQUEST_BODY},
)
async def preview_scraping_action(
    request: Request,
    user: models.User = Depends(get_current_user),
) -> ScrapingAction:
    """Return the structured representation of the requested action."""

    payload = await _parse_relaxed_payload(request, ScrapingActionPreviewRequest)
    return _generate_action(payload)


@router.post(
    "/routines/{routine_id}/actions",
    response_model=ScrapingRoutineResponse,
    openapi_extra={"requestBody": MUTATION_REQUEST_BODY},
)
async def append_scraping_action(
    routine_id: int,
    request: Request,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingRoutineResponse:
    """Append a new action to an existing routine."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    payload = await _parse_relaxed_payload(request, ScrapingActionMutationRequest)
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
    openapi_extra={"requestBody": MUTATION_REQUEST_BODY},
)
async def patch_scraping_action(
    routine_id: int,
    action_index: int,
    request: Request,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingRoutineResponse:
    """Replace an action in a routine using new natural language instructions."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    actions = routine.get_actions()
    if action_index < 0 or action_index >= len(actions):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")

    payload = await _parse_relaxed_payload(request, ScrapingActionMutationRequest)
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


@router.post(
    "/routines/{routine_id}/execute",
    response_model=ScrapingExecutionResponse,
)
async def execute_scraping_routine(
    routine_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingExecutionResponse:
    """Execute the stored actions of a scraping routine using the open browser."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    user_id = str(user.id)
    try:
        page = get_active_page(user_id)
    except BrowserSessionNotFound:
        try:
            await open_webpage(routine.url, user_id)
        except Exception as exc:  # pragma: no cover - network / browser failure
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail="Failed to open browser session",
            ) from exc
        page = get_active_page(user_id)

    credentials = RoutineCredentials(
        email=routine.email,
        password=decrypt_str(routine.password_encrypted),
    )
    outcome = await execute_scraping_routine_service(
        routine=routine,
        page=page,
        credentials=credentials,
    )
    return ScrapingExecutionResponse(
        routine_id=routine.id,
        url=outcome.url,
        results=outcome.results,
    )


__all__ = ["router"]
