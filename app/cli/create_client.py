"""CLI utility for creating client credential entries."""
from __future__ import annotations

import secrets
import uuid
from typing import List

import typer
from sqlalchemy.orm import Session

from app.core.security import encrypt_str
from app.db import models
from app.db.base import get_sessionmaker


def _store_client(name: str, scopes: List[str]) -> tuple[str, str]:
    session_factory = get_sessionmaker()
    session: Session = session_factory()
    try:
        client_id = str(uuid.uuid4())
        client_secret = secrets.token_urlsafe(32)
        client = models.ClientApp(
            name=name,
            client_id=client_id,
            client_secret_encrypted=encrypt_str(client_secret),
        )
        client.set_scopes(scopes)
        session.add(client)
        session.commit()
        return client_id, client_secret
    finally:
        session.close()


def create(
    name: str = typer.Argument(..., help="Nome dell'applicazione client"),
    scope: List[str] = typer.Option(
        [], "--scope", help="Scope da assegnare", show_default=False
    ),
) -> None:
    """Create a new client credentials application."""

    client_id, client_secret = _store_client(name, scope)
    typer.echo("Client creato con successo!")
    typer.echo(f"client_id: {client_id}")
    typer.echo(f"client_secret: {client_secret}")
    typer.echo("Conserva il secret in modo sicuro: non verrà mostrato di nuovo.")


if __name__ == "__main__":
    typer.run(create)
