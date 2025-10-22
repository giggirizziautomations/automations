"""CLI utility to create administrator users."""
from __future__ import annotations

from typing import List, Optional, Sequence

import click
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
            raise click.BadParameter("User with this email already exists")
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


def _prompt_password() -> str:
    """Prompt the user for a password and confirmation."""

    while True:
        password = click.prompt("Password", hide_input=True)
        confirmation = click.prompt("Conferma password", hide_input=True)
        if password == confirmation:
            return password
        click.echo("Le password non coincidono, riprova.", err=True)


def _merge_scopes(option_scopes: Optional[Sequence[str]], argument_scopes: Sequence[str]) -> List[str]:
    scopes: List[str] = []
    if option_scopes:
        scopes.extend(option_scopes)
    scopes.extend(argument_scopes)
    if not scopes:
        scopes = ["*"]
    return scopes


@click.command()
@click.argument("name")
@click.argument("surname")
@click.argument("email")
@click.argument("password_argument", required=False)
@click.argument("scope_arguments", nargs=-1)
@click.option(
    "--password",
    "password_option",
    help="Password per l'amministratore (può essere fornita anche come argomento posizionale)",
)
@click.option(
    "--scope",
    "--scopes",
    "scope_option",
    multiple=True,
    help=(
        "Scope da assegnare. Può essere specificato più volte o fornito come argomento posizionale. "
        "Sono accettati sia --scope che --scopes per retrocompatibilità."
    ),
)
def create(
    name: str,
    surname: str,
    email: str,
    password_argument: Optional[str],
    scope_arguments: Sequence[str],
    password_option: Optional[str],
    scope_option: Sequence[str],
) -> None:
    """Create a new administrator user."""

    if password_option and password_argument:
        raise click.BadParameter(
            "La password non può essere specificata sia come argomento posizionale sia con --password.",
            param_hint="password",
        )

    password = password_option or password_argument
    if password is None:
        password = _prompt_password()

    scopes = _merge_scopes(scope_option, scope_arguments)

    user = _create_admin(
        name=name,
        surname=surname,
        email=email,
        password=password,
        scopes=scopes,
    )
    click.echo(f"Amministratore creato con id={user.id} ed email={user.email}")


if __name__ == "__main__":
    create()
