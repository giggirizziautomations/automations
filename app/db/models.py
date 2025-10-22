"""Database models for users and client applications."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.security import normalize_scopes, scopes_to_string
from app.db.base import Base


class User(Base):
    """Represents a system user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_encrypted = Column(Text, nullable=False)
    scopes = Column(Text, nullable=False, default="")
    is_admin = Column(Boolean, default=False, nullable=False)
    aad_tenant_id = Column(String(255), nullable=True)
    aad_public_client_id = Column(String(255), nullable=True)
    aad_token_cache_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def set_scopes(self, scopes: list[str]) -> None:
        self.scopes = scopes_to_string(scopes)

    def get_scopes(self) -> list[str]:
        return normalize_scopes(self.scopes)


class ClientApp(Base):
    """Client credentials application."""

    __tablename__ = "client_apps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    client_id = Column(String(255), nullable=False, unique=True, index=True)
    client_secret_encrypted = Column(Text, nullable=False)
    scopes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def set_scopes(self, scopes: list[str]) -> None:
        self.scopes = scopes_to_string(scopes)

    def get_scopes(self) -> list[str]:
        return normalize_scopes(self.scopes)


__all__ = ["User", "ClientApp"]
