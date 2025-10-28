"""Database models for users and client applications."""
from __future__ import annotations

from datetime import datetime

from typing import Any, List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

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


class ScrapingRoutine(Base):
    """Persisted scraping instructions authored by a user."""

    __tablename__ = "scraping_routines"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    mode = Column(String(20), nullable=False, default="headless")
    actions = Column(JSON, nullable=False, default=list)
    email = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def get_actions(self) -> List[dict[str, Any]]:
        return list(self.actions or [])

    def set_actions(self, actions: List[dict[str, Any]]) -> None:
        self.actions = actions


__all__ = ["User", "ClientApp", "ScrapingRoutine"]
