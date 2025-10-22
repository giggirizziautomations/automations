"""CLI utility to create administrator users."""
from __future__ import annotations

from typing import List

import typer
from sqlalchemy.orm import Session

from app.core.security import encrypt_str
from app.db import models
from app.db.base import get_sessionmaker


def _create_admin(
    *,
    name: str,
    surname: str,
    email: str,
    password: str,
    scopes: List[str],
) -> models.User:
    session_factory = get_sessionmaker()
    session: Session = session_factory()
    try:
        existing = session.query(models.User).filter(models.User.email == email).first()
        if existing:
            raise typer.BadParameter("User with this email already exists")
        user = models.User(
            name=name,
            surname=surname,
            email=email,
            password_encrypted=encrypt_str(password),
            is_admin=True,
        )
        user.set_scopes(scopes or ["*"])
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def create(
    name: str = typer.Argument(..., help="Nome"),
    surname: str = typer.Argument(..., help="Cognome"),
    email: str = typer.Argument(..., help="Email"),
    password: str = typer.Option(
        ..., "--password", prompt=True, confirmation_prompt=True, hide_input=True
    ),
    scope: List[str] = typer.Option(
        ["*"], "--scope", "--scopes", help="Scope da assegnare"
    ),
) -> None:
    """Create a new administrator user."""

    user = _create_admin(
        name=name,
        surname=surname,
        email=email,
        password=password,
        scopes=scope,
    )
    typer.echo(f"Amministratore creato con id={user.id} ed email={user.email}")


if __name__ == "__main__":
    typer.run(create)
