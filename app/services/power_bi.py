"""Business logic for orchestrating Power BI report exports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import encrypt_str
from app.db import models
from app.schemas.power_bi import (
    PowerBIConfigRequest,
    PowerBIConfigResponse,
    PowerBIExportResponse,
    PowerBIRunRequest,
)
from app.schemas.scraping import ScrapingAction


def _load_scraping_actions(
    actions: Sequence[dict[str, object]] | None,
) -> list[ScrapingAction]:
    """Convert raw JSON payloads into :class:`ScrapingAction` instances."""

    if not actions:
        return []
    return [ScrapingAction.model_validate(action) for action in actions]


def _dump_scraping_actions(
    actions: Sequence[ScrapingAction],
) -> list[dict[str, object]]:
    """Serialize :class:`ScrapingAction` objects into JSON storable dicts."""

    if not actions:
        return []
    return [action.model_dump(mode="json") for action in actions]


def serialize_config(model: models.PowerBIServiceConfig) -> PowerBIConfigResponse:
    return PowerBIConfigResponse(
        id=model.id,
        report_url=model.report_url,
        export_format=model.export_format,
        merge_strategy=model.merge_strategy,
        username=model.username,
        has_password=bool(model.password_encrypted),
        scraping_actions=_load_scraping_actions(model.scraping_actions),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _serialize_export(record: models.PowerBIExportRecord) -> PowerBIExportResponse:
    return PowerBIExportResponse(
        id=record.id,
        vin=record.vin,
        status=record.status,
        export_format=record.export_format,
        report_url=record.report_url,
        payload=record.payload or {},
        notes=record.notes,
        created_at=record.created_at,
        merged_at=record.merged_at,
        updated_at=record.updated_at,
    )


def get_configuration(db: Session) -> models.PowerBIServiceConfig | None:
    """Return the configured Power BI integration if present."""

    return (
        db.query(models.PowerBIServiceConfig)
        .order_by(models.PowerBIServiceConfig.id.asc())
        .first()
    )


def upsert_configuration(
    *, db: Session, payload: PowerBIConfigRequest
) -> PowerBIConfigResponse:
    """Create or update the Power BI configuration from ``payload``."""

    config = get_configuration(db)
    if config is None:
        config = models.PowerBIServiceConfig(
            report_url=str(payload.report_url),
            export_format="xlsx",
            merge_strategy=payload.merge_strategy,
            username=payload.username,
            scraping_actions=_dump_scraping_actions(payload.scraping_actions),
        )
        if payload.password:
            config.password_encrypted = encrypt_str(payload.password)
        db.add(config)
    else:
        config.report_url = str(payload.report_url)
        config.export_format = "xlsx"
        config.merge_strategy = payload.merge_strategy
        config.username = payload.username
        if payload.password:
            config.password_encrypted = encrypt_str(payload.password)
        config.scraping_actions = _dump_scraping_actions(payload.scraping_actions)
    db.commit()
    db.refresh(config)
    return serialize_config(config)


def _load_routine_with_actions(
    db: Session, routine_id: int
) -> tuple[models.ScrapingRoutine, list[ScrapingAction]]:
    routine = (
        db.query(models.ScrapingRoutine)
        .filter(models.ScrapingRoutine.id == routine_id)
        .first()
    )
    if routine is None:
        raise LookupError("Scraping routine not found")
    actions = [ScrapingAction.model_validate(item) for item in routine.get_actions()]
    return routine, actions


def apply_scraping_routine(*, db: Session, routine_id: int) -> PowerBIConfigResponse:
    """Copy actions from a scraping routine into the Power BI configuration."""

    config = get_configuration(db)
    if config is None:
        raise ValueError("Power BI service configuration is missing")

    routine, actions = _load_routine_with_actions(db, routine_id)
    config.scraping_actions = _dump_scraping_actions(actions)
    config.export_format = "xlsx"
    db.add(config)
    db.commit()
    db.refresh(config)
    return serialize_config(config)


def run_export(*, db: Session, payload: PowerBIRunRequest) -> PowerBIExportResponse:
    """Simulate scraping, downloading and merging a Power BI report."""

    config = get_configuration(db)
    if config is None:
        raise ValueError("Power BI service configuration is missing")

    routine, routine_actions = _load_routine_with_actions(db, payload.routine_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    prepared_payload = {
        "vin": payload.vin,
        "parameters": payload.parameters,
        "merge_strategy": config.merge_strategy,
        "export_format": config.export_format,
        "generated_at": now.isoformat(),
        "routine_id": routine.id,
        "routine_url": routine.url,
        "routine_mode": routine.mode,
        "scraping_actions": [
            action.model_dump(mode="json") for action in routine_actions
        ],
    }

    record = models.PowerBIExportRecord(
        vin=payload.vin.upper(),
        report_url=config.report_url,
        export_format=config.export_format,
        status="completed",
        payload=prepared_payload,
        notes=payload.notes,
        created_at=now,
        merged_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _serialize_export(record)


def list_exports(db: Session) -> list[PowerBIExportResponse]:
    """Return all stored export records."""

    records: Iterable[models.PowerBIExportRecord] = (
        db.query(models.PowerBIExportRecord)
        .order_by(models.PowerBIExportRecord.created_at.desc())
        .all()
    )
    return [_serialize_export(record) for record in records]


def search_exports_by_vin(db: Session, vin: str) -> list[PowerBIExportResponse]:
    """Return all export records matching ``vin`` (case insensitive)."""

    vin_normalised = vin.strip()
    if not vin_normalised:
        return []
    records: Iterable[models.PowerBIExportRecord] = (
        db.query(models.PowerBIExportRecord)
        .filter(
            func.lower(models.PowerBIExportRecord.vin)
            == vin_normalised.lower()
        )
        .order_by(models.PowerBIExportRecord.created_at.desc())
        .all()
    )
    return [_serialize_export(record) for record in records]


__all__ = [
    "apply_scraping_routine",
    "get_configuration",
    "list_exports",
    "run_export",
    "serialize_config",
    "search_exports_by_vin",
    "upsert_configuration",
]
