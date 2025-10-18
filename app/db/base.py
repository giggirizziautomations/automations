"""Database session and base model utilities."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings


Base = declarative_base()
_SessionLocal: sessionmaker | None = None
_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a SQLAlchemy engine configured using current settings."""

    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    """Return a sessionmaker bound to the engine."""

    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


def get_db() -> Generator:
    """Provide a transactional scope around a series of operations."""

    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def reset_database_state() -> None:
    """Reset cached engine/session factory. Useful for testing."""

    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None


__all__ = [
    "Base",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "reset_database_state",
]
