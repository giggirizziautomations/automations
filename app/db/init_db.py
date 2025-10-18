"""Database initialisation script."""
from __future__ import annotations

from app.db import models  # noqa: F401
from app.db.base import Base, get_engine


def init_db() -> None:
    """Create database tables based on metadata."""

    engine = get_engine()
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
