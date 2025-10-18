"""Tests for the create_admin CLI helper."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.cli.create_admin import _create_admin
from app.core import security
from app.db import models


def test_create_admin_cli(db_session: Session) -> None:
    user = _create_admin(
        name="Admin",
        surname="User",
        email="admin@example.com",
        password="adminpass",
        scopes=["*"]
    )

    persisted = db_session.query(models.User).filter_by(email="admin@example.com").first()
    assert persisted is not None
    assert persisted.is_admin is True
    assert security.decrypt_str(persisted.password_encrypted) == "adminpass"
    assert persisted.get_scopes() == ["*"]
