"""Lightweight DuckDB-compatible stub backed by SQLite for testing."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence


class DuckDBPyConnection:
    """Subset of the DuckDB connection API using SQLite under the hood."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)

    def execute(
        self, query: str, parameters: Sequence[object] | None = None
    ) -> sqlite3.Cursor:
        cursor = self._connection.cursor()
        if parameters is None:
            cursor.execute(query)
        else:
            cursor.execute(query, tuple(parameters))
        self._connection.commit()
        return cursor

    def executemany(
        self, query: str, parameters: Iterable[Sequence[object]]
    ) -> sqlite3.Cursor:
        cursor = self._connection.cursor()
        cursor.executemany(query, list(parameters))
        self._connection.commit()
        return cursor

    def close(self) -> None:
        self._connection.close()


def connect(path: str) -> DuckDBPyConnection:
    """Return a DuckDB-like connection backed by SQLite."""

    return DuckDBPyConnection(path)


__all__ = ["DuckDBPyConnection", "connect"]
