"""Shared pytest fixtures."""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Generator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import reload_settings
from app.db.base import get_sessionmaker, reset_database_state
from app.db.init_db import init_db


@pytest.fixture()
def test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Prepare environment variables and initialise the database."""

    key = Fernet.generate_key().decode()
    db_path = tmp_path / "test.db"
    duckdb_path = tmp_path / "exports.duckdb"
    monkeypatch.setenv("FERNET_KEY", key)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("DUCKDB_PATH", str(duckdb_path))

    reload_settings()
    security.get_fernet.cache_clear()  # type: ignore[attr-defined]
    reset_database_state()
    init_db()
    return db_path


@pytest.fixture()
def api_client(test_environment: Path) -> Generator[TestClient, None, None]:
    """Return a TestClient instance with a fresh application state."""

    import app.main

    importlib.reload(app.main)

    client = TestClient(app.main.app)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture()
def db_session(test_environment: Path):
    """Provide a SQLAlchemy session bound to the test database."""

    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
