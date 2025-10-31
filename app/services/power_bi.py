"""Business logic for orchestrating Power BI report exports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.core.security import encrypt_str
from app.db import models
from app.schemas.power_bi import (
    PowerBIConfigRequest,
    PowerBIConfigResponse,
    PowerBIExportResponse,
    PowerBIMergedRow,
    PowerBIRunRequest,
)
from app.schemas.scraping import ScrapingAction
from app.services import power_bi_storage


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
        user_id=model.user_id,
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
        config_id=record.config_id,
        routine_id=record.routine_id,
        vin=record.vin,
        status=record.status,
        export_format=record.export_format,
        report_url=record.report_url,
        dedup_parameter=record.dedup_parameter,
        payload=record.payload or {},
        notes=record.notes,
        created_at=record.created_at,
        merged_at=record.merged_at,
        updated_at=record.updated_at,
    )


def list_configurations(*, db: Session, user_id: int) -> list[PowerBIConfigResponse]:
    """Return all Power BI configurations owned by ``user_id``."""

    configs: Iterable[models.PowerBIServiceConfig] = (
        db.query(models.PowerBIServiceConfig)
        .filter(models.PowerBIServiceConfig.user_id == user_id)
        .order_by(models.PowerBIServiceConfig.created_at.asc())
        .all()
    )
    return [serialize_config(config) for config in configs]


def _get_configuration_by_id(
    *, db: Session, user_id: int, config_id: int
) -> models.PowerBIServiceConfig:
    config = (
        db.query(models.PowerBIServiceConfig)
        .filter(
            models.PowerBIServiceConfig.id == config_id,
            models.PowerBIServiceConfig.user_id == user_id,
        )
        .first()
    )
    if config is None:
        raise LookupError("Power BI service configuration is missing")
    return config


def get_configuration_by_id(
    *, db: Session, user_id: int, config_id: int
) -> PowerBIConfigResponse:
    """Return a single configuration owned by ``user_id``."""

    config = _get_configuration_by_id(db=db, user_id=user_id, config_id=config_id)
    return serialize_config(config)


def upsert_configuration(
    *, db: Session, user_id: int, payload: PowerBIConfigRequest
) -> PowerBIConfigResponse:
    """Create or update a Power BI configuration from ``payload``."""

    if payload.config_id is not None:
        config = (
            db.query(models.PowerBIServiceConfig)
            .filter(
                models.PowerBIServiceConfig.id == payload.config_id,
                models.PowerBIServiceConfig.user_id == user_id,
            )
            .first()
        )
        if config is None:
            raise LookupError("Power BI service configuration is missing")
    else:
        config = models.PowerBIServiceConfig(
            user_id=user_id,
            report_url=str(payload.report_url),
            export_format="xlsx",
            merge_strategy=payload.merge_strategy,
            username=payload.username,
            scraping_actions=_dump_scraping_actions(payload.scraping_actions),
        )
        if payload.password:
            config.password_encrypted = encrypt_str(payload.password)
        db.add(config)
        db.commit()
        db.refresh(config)
        return serialize_config(config)

    config.report_url = str(payload.report_url)
    config.export_format = "xlsx"
    config.merge_strategy = payload.merge_strategy
    config.username = payload.username
    if payload.password:
        config.password_encrypted = encrypt_str(payload.password)
    config.scraping_actions = _dump_scraping_actions(payload.scraping_actions)
    db.add(config)
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


def apply_scraping_routine(
    *, db: Session, user_id: int, config_id: int, routine_id: int
) -> PowerBIConfigResponse:
    """Copy actions from a scraping routine into the Power BI configuration."""

    config = _get_configuration_by_id(db=db, user_id=user_id, config_id=config_id)
    routine, actions = _load_routine_with_actions(db, routine_id)
    config.scraping_actions = _dump_scraping_actions(actions)
    config.export_format = "xlsx"
    db.add(config)
    db.commit()
    db.refresh(config)
    return serialize_config(config)


def _merge_datasets(
    datasets: Sequence[Sequence[dict[str, object]]], dedup_parameter: str
) -> list[dict[str, object]]:
    if not datasets:
        raise ValueError("At least one dataset must be provided")

    merged: dict[str, dict[str, object]] = {}
    for dataset in datasets:
        for row in dataset:
            if dedup_parameter not in row:
                raise ValueError(
                    f"Row missing deduplication parameter '{dedup_parameter}'"
                )
            key = str(row[dedup_parameter])
            merged[key] = dict(row)
    return list(merged.values())


def run_export(
    *,
    db: Session,
    user_id: int,
    config_id: int,
    payload: PowerBIRunRequest,
) -> PowerBIExportResponse:
    """Simulate scraping, downloading and merging a Power BI report."""

    config = _get_configuration_by_id(db=db, user_id=user_id, config_id=config_id)
    routine, routine_actions = _load_routine_with_actions(db, payload.routine_id)

    merged_rows = _merge_datasets(payload.datasets, payload.dedup_parameter)

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
        "dedup_parameter": payload.dedup_parameter,
        "merged_row_count": len(merged_rows),
    }

    record = models.PowerBIExportRecord(
        config_id=config.id,
        routine_id=routine.id,
        vin=payload.vin.upper(),
        report_url=config.report_url,
        export_format=config.export_format,
        status="completed",
        dedup_parameter=payload.dedup_parameter,
        payload=prepared_payload,
        notes=payload.notes,
        created_at=now,
        merged_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    power_bi_storage.store_rows(
        export_id=record.id,
        routine_id=routine.id,
        config_id=config.id,
        dedup_parameter=payload.dedup_parameter,
        rows=merged_rows,
    )

    return _serialize_export(record)


def list_exports(db: Session) -> list[PowerBIExportResponse]:
    """Return all stored export records."""

    records: Iterable[models.PowerBIExportRecord] = (
        db.query(models.PowerBIExportRecord)
        .order_by(models.PowerBIExportRecord.created_at.desc())
        .all()
    )
    return [_serialize_export(record) for record in records]


def get_export_dataset(routine_id: int) -> list[PowerBIMergedRow]:
    """Return merged dataset rows for ``routine_id`` from DuckDB."""

    rows = power_bi_storage.fetch_by_routine_id(routine_id)
    return [PowerBIMergedRow.model_validate(row) for row in rows]


def search_export_dataset_by_parameter(
    parameter: str, value: str
) -> list[PowerBIMergedRow]:
    """Return merged dataset rows filtered by ``parameter`` and ``value``."""

    rows = power_bi_storage.fetch_by_parameter(parameter, value)
    return [PowerBIMergedRow.model_validate(row) for row in rows]


__all__ = [
    "apply_scraping_routine",
    "get_configuration_by_id",
    "get_export_dataset",
    "list_configurations",
    "list_exports",
    "run_export",
    "search_export_dataset_by_parameter",
    "serialize_config",
    "upsert_configuration",
]
