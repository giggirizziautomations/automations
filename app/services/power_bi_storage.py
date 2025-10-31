"""DuckDB-backed persistence for Power BI merged datasets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

try:  # pragma: no cover - exercised via runtime import
    import duckdb  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    from app.services import duckdb_stub as duckdb

from app.core.config import get_settings

_TABLE_NAME = "power_bi_export_rows"


def _get_database_path() -> Path:
    settings = get_settings()
    path = Path(settings.duckdb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
            export_id BIGINT,
            routine_id BIGINT,
            config_id BIGINT,
            dedup_parameter TEXT,
            parameter_value TEXT,
            row JSON
        )
        """
    )


def store_rows(
    *,
    export_id: int,
    routine_id: int,
    config_id: int,
    dedup_parameter: str,
    rows: Sequence[dict[str, object]],
) -> None:
    """Persist the merged dataset produced by a Power BI export."""

    db_path = _get_database_path()
    connection = duckdb.connect(str(db_path))
    try:
        _ensure_schema(connection)
        connection.execute(
            f"DELETE FROM {_TABLE_NAME} WHERE routine_id = ?", (routine_id,)
        )
        if not rows:
            return
        prepared: Iterable[tuple[int, int, int, str, str, str]] = (
            (
                export_id,
                routine_id,
                config_id,
                dedup_parameter,
                str(row[dedup_parameter]),
                json.dumps(row),
            )
            for row in rows
        )
        connection.executemany(
            f"""
            INSERT INTO {_TABLE_NAME}
            (export_id, routine_id, config_id, dedup_parameter, parameter_value, row)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            list(prepared),
        )
    finally:
        connection.close()


def fetch_by_routine_id(routine_id: int) -> list[dict[str, object]]:
    """Return merged rows associated with ``routine_id``."""

    db_path = _get_database_path()
    connection = duckdb.connect(str(db_path))
    try:
        _ensure_schema(connection)
        results = connection.execute(
            f"""
            SELECT export_id, routine_id, config_id, dedup_parameter, parameter_value, row
            FROM {_TABLE_NAME}
            WHERE routine_id = ?
            ORDER BY parameter_value
            """,
            (routine_id,),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "export_id": export_id,
            "routine_id": routine_id,
            "config_id": config_id,
            "dedup_parameter": dedup_parameter,
            "parameter_value": parameter_value,
            "data": json.loads(row_json),
        }
        for export_id, routine_id, config_id, dedup_parameter, parameter_value, row_json in results
    ]


def fetch_by_parameter(parameter: str, value: str) -> list[dict[str, object]]:
    """Return merged rows matching ``parameter`` and ``value``."""

    db_path = _get_database_path()
    connection = duckdb.connect(str(db_path))
    try:
        _ensure_schema(connection)
        results = connection.execute(
            f"""
            SELECT export_id, routine_id, config_id, dedup_parameter, parameter_value, row
            FROM {_TABLE_NAME}
            WHERE dedup_parameter = ? AND parameter_value = ?
            ORDER BY export_id
            """,
            (parameter, value),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "export_id": export_id,
            "routine_id": routine_id,
            "config_id": config_id,
            "dedup_parameter": dedup_parameter,
            "parameter_value": parameter_value,
            "data": json.loads(row_json),
        }
        for export_id, routine_id, config_id, dedup_parameter, parameter_value, row_json in results
    ]


__all__ = ["store_rows", "fetch_by_routine_id", "fetch_by_parameter"]
