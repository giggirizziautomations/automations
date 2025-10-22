"""Helpers for provisioning client credentials records."""
from __future__ import annotations

from typing import Sequence

import secrets
from sqlalchemy.orm import Session

from app.core.security import encrypt_str
from app.db import models
from app.db.base import get_sessionmaker


def _normalize_scopes(scopes: Sequence[str] | None) -> list[str]:
    return [scope.strip() for scope in (scopes or []) if scope.strip()]


def generate_client_secret() -> str:
    """Generate a 64-character random secret."""

    return secrets.token_hex(32)


def create_client_application(
    *, name: str, client_id: str, scopes: Sequence[str] | None = None
) -> tuple[models.ClientApp, str]:
    """Persist a client application using an admin-provided identifier."""

    session_factory = get_sessionmaker()
    session: Session = session_factory()
    try:
        normalized_name = name.strip()
        normalized_client_id = client_id.strip()
        if not normalized_name:
            raise ValueError("Il nome dell'applicazione client non può essere vuoto.")
        if not normalized_client_id:
            raise ValueError("Il client_id deve contenere almeno un carattere.")

        existing = (
            session.query(models.ClientApp)
            .filter(models.ClientApp.client_id == normalized_client_id)
            .first()
        )
        if existing:
            raise ValueError(
                "Esiste già un'applicazione client con il client_id specificato."
            )

        secret = generate_client_secret()
        client = models.ClientApp(
            name=normalized_name,
            client_id=normalized_client_id,
            client_secret_encrypted=encrypt_str(secret),
        )
        client.set_scopes(_normalize_scopes(scopes))
        session.add(client)
        session.commit()
        session.refresh(client)
        return client, secret
    finally:
        session.close()


__all__ = ["create_client_application", "generate_client_secret"]
