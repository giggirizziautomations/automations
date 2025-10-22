"""CLI utility for creating client credential entries."""
from __future__ import annotations

import secrets
import uuid
from typing import List, Optional

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
    name: Optional[str] = typer.Argument(
        None, help="Nome dell'applicazione client"
    ),
    scope: Optional[List[str]] = typer.Option(
        None, "--scope", help="Scope da assegnare", show_default=False
    ),
) -> None:
    """Create a new client credentials application."""

    normalized_name = (name or "").strip()
    if not normalized_name:
        typer.secho(
            "Errore: il nome dell'applicazione client non può essere vuoto.",
            err=True,
            fg=typer.colors.RED,
        )
        typer.secho(
            "Esempio: python -m app.cli.create_client my-app --scope reports:read",
            err=True,
        )
        raise typer.Exit(code=1)

    client_scopes = scope or []

    client_id, client_secret = _store_client(normalized_name, client_scopes)
    typer.echo("Client creato con successo!")
    typer.echo(f"client_id: {client_id}")
    typer.echo(f"client_secret: {client_secret}")
    typer.echo("Conserva il secret in modo sicuro: non verrà mostrato di nuovo.")


if __name__ == "__main__":
    typer.run(create)
