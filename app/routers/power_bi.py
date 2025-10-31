"""Endpoints powering the Power BI scraping and export service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import require_admin, require_admin_or_scopes
from app.db.base import get_db
from app.schemas.power_bi import (
    PowerBIConfigRequest,
    PowerBIConfigResponse,
    PowerBIExportResponse,
    PowerBIRunRequest,
    PowerBIScrapingRoutineRequest,
)
from app.services import power_bi as power_bi_service


router = APIRouter(prefix="/power-bi", tags=["power-bi"])


@router.get(
    "/config",
    response_model=PowerBIConfigResponse,
    dependencies=[Depends(require_admin_or_scopes(["bi"]))],
)
def get_power_bi_config(db: Session = Depends(get_db)) -> PowerBIConfigResponse:
    """Return the current Power BI integration configuration."""

    config = power_bi_service.get_configuration(db)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Power BI service not configured",
        )
    return power_bi_service.serialize_config(config)


@router.put(
    "/config",
    response_model=PowerBIConfigResponse,
    dependencies=[Depends(require_admin_or_scopes(["bi"]))],
)
def put_power_bi_config(
    payload: PowerBIConfigRequest,
    db: Session = Depends(get_db),
) -> PowerBIConfigResponse:
    """Create or update the Power BI integration configuration."""

    return power_bi_service.upsert_configuration(db=db, payload=payload)


@router.post(
    "/run",
    response_model=PowerBIExportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_scopes(["bi"]))],
)
def trigger_power_bi_run(
    payload: PowerBIRunRequest,
    db: Session = Depends(get_db),
) -> PowerBIExportResponse:
    """Trigger the automated scraping, download and merge routine."""

    try:
        return power_bi_service.run_export(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch(
    "/config/scraping-actions",
    response_model=PowerBIConfigResponse,
    dependencies=[Depends(require_admin_or_scopes(["bi"]))],
)
def patch_power_bi_scraping_actions(
    payload: PowerBIScrapingRoutineRequest,
    db: Session = Depends(get_db),
) -> PowerBIConfigResponse:
    """Import scraping actions from an existing scraping routine."""

    try:
        return power_bi_service.apply_scraping_routine(
            db=db, routine_id=payload.routine_id
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
    "/admin/exports/by-vin/{vin}",
    response_model=list[PowerBIExportResponse],
    dependencies=[Depends(require_admin)],
)
def search_power_bi_exports_by_vin(
    vin: str,
    db: Session = Depends(get_db),
) -> list[PowerBIExportResponse]:
    """Return all stored exports that match the provided VIN."""

    return power_bi_service.search_exports_by_vin(db, vin)


__all__ = ["router"]
