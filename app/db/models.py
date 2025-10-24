"""Database models for users and client applications."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship

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

    scraping_targets = relationship(
        "ScrapingTarget",
        back_populates="user",
        cascade="all, delete-orphan",
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


class ScrapingTarget(Base):
    """Scraping configuration for a specific user and site."""

    __tablename__ = "scraping_targets"
    __table_args__ = (
        UniqueConstraint("user_id", "site_name", name="uq_scraping_target_user_site"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    site_name = Column(String(150), nullable=False)
    url = Column(String(2048), nullable=False)
    recipe = Column(String(100), nullable=False, default="default")
    parameters = Column(Text, nullable=False, default="{}")
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="scraping_targets")

    def __repr__(self) -> str:
        return (
            "ScrapingTarget(id={id}, user_id={user_id}, site_name={site_name}, url={url})".format(
                id=self.id,
                user_id=self.user_id,
                site_name=self.site_name,
                url=self.url,
            )
        )


__all__ = ["User", "ClientApp", "ScrapingTarget"]
