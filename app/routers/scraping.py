"""Endpoints supporting the scraping instruction workflow."""
from __future__ import annotations

import json
from typing import Any, TypeVar

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
from app.schemas.power_automate import PowerAutomateInvocationRequest
from app.services import power_automate as power_automate_service
from app.services.scraping_executor import (
    CustomActionResult,
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


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _extract_from_path(data: Any, path: str) -> Any:
    current = data
    for chunk in path.split("."):
        chunk = chunk.strip()
        if not chunk:
            return None
        if isinstance(current, dict):
            current = current.get(chunk)
        elif isinstance(current, (list, tuple)):
            try:
                index = int(chunk)
            except ValueError:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _set_nested_value(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [chunk.strip() for chunk in path.split(".") if chunk.strip()]
    if not parts:
        return
    cursor = target
    for chunk in parts[:-1]:
        existing = cursor.get(chunk)
        if not isinstance(existing, dict):
            existing = {}
            cursor[chunk] = existing
        cursor = existing
    cursor[parts[-1]] = value


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
    session_id: str | None = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapingExecutionResponse:
    """Execute the stored actions of a scraping routine using the open browser."""

    routine = _get_owned_routine(db=db, routine_id=routine_id, user=user)
    user_id = str(user.id)
    try:
        page = get_active_page(user_id, session_id=session_id)
    except BrowserSessionNotFound:
        try:
            await open_webpage(routine.url, user_id, session_id=session_id)
        except Exception as exc:  # pragma: no cover - network / browser failure
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail="Failed to open browser session",
            ) from exc
        page = get_active_page(user_id, session_id=session_id)

    credentials = RoutineCredentials(
        email=routine.email,
        password=decrypt_str(routine.password_encrypted),
    )

    async def _handle_custom_action(
        action: ScrapingAction,
        resolved_credentials: RoutineCredentials,
        context: dict[str, Any],
    ) -> CustomActionResult | None:
        metadata = action.metadata or {}
        if not isinstance(metadata, dict):
            return CustomActionResult(status="skipped", detail="Unsupported custom action metadata")

        flow_identifier = metadata.get("power_automate_flow_id")
        flow_id = _coerce_int(flow_identifier)
        if flow_id is None:
            return None

        template_variables: dict[str, Any] = {
            "context": context,
            "credentials": {
                "email": resolved_credentials.email,
                "password": resolved_credentials.password,
            },
            "user": {"id": user.id, "email": user.email},
        }
        extra_variables = metadata.get("variables")
        if isinstance(extra_variables, dict):
            template_variables.update(extra_variables)

        parameters = power_automate_service.render_template(
            _safe_dict(metadata.get("parameters")), template_variables
        )
        body_overrides = power_automate_service.render_template(
            _safe_dict(metadata.get("body_overrides")), template_variables
        )
        query_params = power_automate_service.render_template(
            _safe_dict(metadata.get("query_params")), template_variables
        )
        failure_parameters = power_automate_service.render_template(
            _safe_dict(metadata.get("failure_parameters")), template_variables
        )
        failure_body_overrides = power_automate_service.render_template(
            _safe_dict(metadata.get("failure_body_overrides")), template_variables
        )
        failure_query_params = power_automate_service.render_template(
            _safe_dict(metadata.get("failure_query_params")), template_variables
        )

        wait_for_completion = bool(metadata.get("wait_for_completion", True))
        timeout_seconds = _coerce_int(metadata.get("timeout_seconds"))
        failure_flow_id = _coerce_int(metadata.get("failure_flow_id"))

        invocation = PowerAutomateInvocationRequest(
            parameters=_safe_dict(parameters),
            body_overrides=_safe_dict(body_overrides),
            query_params=_safe_dict(query_params),
            wait_for_completion=wait_for_completion,
            timeout_seconds=timeout_seconds,
            failure_flow_id=failure_flow_id,
            failure_parameters=_safe_dict(failure_parameters),
            failure_body_overrides=_safe_dict(failure_body_overrides),
            failure_query_params=_safe_dict(failure_query_params),
        )

        try:
            result = await power_automate_service.invoke_flow(
                db=db,
                user_id=user.id,
                flow_id=flow_id,
                payload=invocation,
                template_variables=template_variables,
            )
        except LookupError as exc:
            return CustomActionResult(status="error", detail=str(exc))

        context_updates: dict[str, Any] = {}
        response_payload = result.response
        store_as = metadata.get("store_response_as")
        if isinstance(store_as, str) and store_as.strip():
            context_updates[store_as.strip()] = response_payload
        field_mapping = metadata.get("store_response_fields")
        if isinstance(field_mapping, dict) and isinstance(response_payload, (dict, list)):
            for source_path, target_path in field_mapping.items():
                if not isinstance(source_path, str) or not isinstance(target_path, str):
                    continue
                extracted = _extract_from_path(response_payload, source_path)
                if extracted is not None:
                    _set_nested_value(context_updates, target_path, extracted)

        detail = result.detail
        if detail is None and result.status == "success":
            detail = "Flow executed successfully"

        return CustomActionResult(
            status=result.status,
            detail=detail,
            context_updates=context_updates,
        )

    outcome = await execute_scraping_routine_service(
        routine=routine,
        page=page,
        credentials=credentials,
        custom_action_handler=_handle_custom_action,
    )
    return ScrapingExecutionResponse(
        routine_id=routine.id,
        url=outcome.url,
        results=outcome.results,
    )


__all__ = ["router"]
