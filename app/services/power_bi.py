"""Business logic for orchestrating Power BI report exports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

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


def serialize_config(model: models.PowerBIServiceConfig) -> PowerBIConfigResponse:
    return PowerBIConfigResponse(
        id=model.id,
        report_url=model.report_url,
        export_format=model.export_format,
        merge_strategy=model.merge_strategy,
        username=model.username,
        has_password=bool(model.password_encrypted),
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
            export_format=payload.export_format,
            merge_strategy=payload.merge_strategy,
            username=payload.username,
        )
        if payload.password:
            config.password_encrypted = encrypt_str(payload.password)
        db.add(config)
    else:
        config.report_url = str(payload.report_url)
        config.export_format = payload.export_format
        config.merge_strategy = payload.merge_strategy
        config.username = payload.username
        if payload.password:
            config.password_encrypted = encrypt_str(payload.password)
    db.commit()
    db.refresh(config)
    return serialize_config(config)


def run_export(*, db: Session, payload: PowerBIRunRequest) -> PowerBIExportResponse:
    """Simulate scraping, downloading and merging a Power BI report."""

    config = get_configuration(db)
    if config is None:
        raise ValueError("Power BI service configuration is missing")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    prepared_payload = {
        "vin": payload.vin,
        "parameters": payload.parameters,
        "merge_strategy": config.merge_strategy,
        "export_format": config.export_format,
        "generated_at": now.isoformat(),
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
    "get_configuration",
    "list_exports",
    "run_export",
    "serialize_config",
    "search_exports_by_vin",
    "upsert_configuration",
]
