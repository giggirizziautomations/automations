"""Endpoints powering the Power BI scraping and export service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_admin, require_admin_or_scopes
from app.db.base import get_db
from app.schemas.power_bi import (
    PowerBIConfigRequest,
    PowerBIConfigResponse,
    PowerBIExportResponse,
    PowerBIMergedRow,
    PowerBIRunRequest,
    PowerBIScrapingRoutineRequest,
)
from app.services import power_bi as power_bi_service


router = APIRouter(prefix="/power-bi", tags=["power-bi"])


def _require_user_id(principal: Principal) -> int:
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User context required",
        )
    return principal.user_id


@router.get(
    "/config",
    response_model=list[PowerBIConfigResponse],
)
def list_power_bi_configs(
    principal: Principal = Depends(require_admin_or_scopes(["bi"])),
    db: Session = Depends(get_db),
) -> list[PowerBIConfigResponse]:
    """Return all Power BI configurations belonging to the current user."""

    user_id = _require_user_id(principal)
    return power_bi_service.list_configurations(db=db, user_id=user_id)


@router.get(
    "/config/{config_id}",
    response_model=PowerBIConfigResponse,
)
def get_power_bi_config_by_id(
    config_id: int,
    principal: Principal = Depends(require_admin_or_scopes(["bi"])),
    db: Session = Depends(get_db),
) -> PowerBIConfigResponse:
    """Return a single configuration belonging to the current user."""

    user_id = _require_user_id(principal)
    try:
        return power_bi_service.get_configuration_by_id(
            db=db, user_id=user_id, config_id=config_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.put(
    "/config",
    response_model=PowerBIConfigResponse,
)
def put_power_bi_config(
    payload: PowerBIConfigRequest,
    principal: Principal = Depends(require_admin_or_scopes(["bi"])),
    db: Session = Depends(get_db),
) -> PowerBIConfigResponse:
    """Create or update the Power BI integration configuration."""

    user_id = _require_user_id(principal)
    try:
        return power_bi_service.upsert_configuration(
            db=db, user_id=user_id, payload=payload
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/run/{config_id}",
    response_model=PowerBIExportResponse,
    status_code=status.HTTP_201_CREATED,
)
def trigger_power_bi_run(
    config_id: int,
    payload: PowerBIRunRequest,
    principal: Principal = Depends(require_admin_or_scopes(["bi"])),
    db: Session = Depends(get_db),
) -> PowerBIExportResponse:
    """Trigger the automated scraping, download and merge routine."""

    user_id = _require_user_id(principal)
    try:
        return power_bi_service.run_export(
            db=db, user_id=user_id, config_id=config_id, payload=payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/config/scraping-actions",
    response_model=PowerBIConfigResponse,
)
def patch_power_bi_scraping_actions(
    payload: PowerBIScrapingRoutineRequest,
    principal: Principal = Depends(require_admin_or_scopes(["bi"])),
    db: Session = Depends(get_db),
) -> PowerBIConfigResponse:
    """Import scraping actions from an existing scraping routine."""

    user_id = _require_user_id(principal)
    try:
        return power_bi_service.apply_scraping_routine(
            db=db,
            user_id=user_id,
            config_id=payload.config_id,
            routine_id=payload.routine_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/admin/exports",
    response_model=list[PowerBIExportResponse],
    dependencies=[Depends(require_admin)],
)
def list_power_bi_exports(db: Session = Depends(get_db)) -> list[PowerBIExportResponse]:
    """List all stored Power BI export records."""

    return power_bi_service.list_exports(db)


@router.get(
    "/admin/exports/{routine_id}",
    response_model=list[PowerBIMergedRow],
    dependencies=[Depends(require_admin)],
)
def get_power_bi_export_dataset(routine_id: int) -> list[PowerBIMergedRow]:
    """Return merged rows stored for ``routine_id``."""

    return power_bi_service.get_export_dataset(routine_id)


@router.get(
    "/admin/exports/by-parameter/{filter_expression}",
    response_model=list[PowerBIMergedRow],
    dependencies=[Depends(require_admin)],
)
def search_power_bi_exports_by_parameter(
    filter_expression: str,
) -> list[PowerBIMergedRow]:
    """Return merged rows filtered using ``parameter:value`` expression."""

    if ":" not in filter_expression:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filter must follow the pattern <parameter>:<value>",
        )
    parameter, value = filter_expression.split(":", 1)
    parameter = parameter.strip()
    value = value.strip()
    if not parameter or not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both parameter and value are required",
        )
    return power_bi_service.search_export_dataset_by_parameter(parameter, value)


__all__ = ["router"]
