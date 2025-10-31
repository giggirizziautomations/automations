"""Endpoints managing user Power Automate flows."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db import models
from app.db.base import get_db
from app.schemas.power_automate import (
    PowerAutomateFlowLoadRequest,
    PowerAutomateFlowRequest,
    PowerAutomateFlowResponse,
    PowerAutomateInvocationRequest,
    PowerAutomateInvocationResponse,
)
from app.services import power_automate as power_automate_service

router = APIRouter(prefix="/power-automate", tags=["power-automate"])


@router.get("/flows", response_model=list[PowerAutomateFlowResponse])
def list_flows(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PowerAutomateFlowResponse]:
    """Return the flows owned by the authenticated user."""

    return power_automate_service.list_flows(db=db, user_id=user.id)


@router.post(
    "/flows",
    response_model=PowerAutomateFlowResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_flow(
    payload: PowerAutomateFlowRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PowerAutomateFlowResponse:
    """Persist a new Power Automate flow for the user."""

    try:
        return power_automate_service.create_flow(db=db, user_id=user.id, payload=payload)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/flows/load",
    response_model=list[PowerAutomateFlowResponse],
)
def load_flows(
    payload: PowerAutomateFlowLoadRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PowerAutomateFlowResponse]:
    """Bulk load or upsert flow definitions for the authenticated user."""

    try:
        return power_automate_service.load_flows(
            db=db,
            user_id=user.id,
            payload=payload,
        )
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put(
    "/flows/{flow_id}",
    response_model=PowerAutomateFlowResponse,
)
def update_flow(
    flow_id: int,
    payload: PowerAutomateFlowRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PowerAutomateFlowResponse:
    """Update an existing flow owned by the user."""

    try:
        return power_automate_service.update_flow(
            db=db,
            user_id=user.id,
            flow_id=flow_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/flows/{flow_id}",
    status_code=status.HTTP_200_OK,
)
def delete_flow(
    flow_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a flow belonging to the authenticated user."""

    try:
        power_automate_service.delete_flow(db=db, user_id=user.id, flow_id=flow_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return None


@router.post(
    "/flows/{flow_id}/invoke",
    response_model=PowerAutomateInvocationResponse,
)
async def invoke_flow(
    flow_id: int,
    payload: PowerAutomateInvocationRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PowerAutomateInvocationResponse:
    """Trigger the selected flow with the provided variables."""

    try:
        result = await power_automate_service.invoke_flow(
            db=db,
            user_id=user.id,
            flow_id=flow_id,
            payload=payload,
            template_variables={"user": {"id": user.id, "email": user.email}},
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return power_automate_service.to_schema(result)


__all__ = ["router"]
