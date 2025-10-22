"""CLI utility for creating client credential entries."""
from __future__ import annotations

from typing import List
from typing import List, Optional

import typer

from app.setup.client_credentials import create_client_application


def create(
    name: str = typer.Argument(..., help="Nome dell'applicazione client"),
    client_id: str = typer.Option(
        ..., "--client-id", "-c", prompt=True, help="Identificativo client scelto dall'amministratore"
    ),
    client_id: Optional[str] = typer.Argument(
        None, help="Identificativo client scelto dall'amministratore"
    ),
    scopes: List[str] = typer.Option(
        [],
        "--scope",
        "-s",
        help="Scope da assegnare (opzione ripetibile)",
        show_default=False,
    ),
) -> None:
    """Create a new client credentials application."""

    normalized_name = name.strip()
    if not normalized_name:
        typer.secho(
            "Errore: il nome dell'applicazione client non può essere vuoto.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    normalized_client_id = client_id.strip()
    if not normalized_client_id:
        typer.secho(
            "Errore: devi specificare un client_id scelto dall'amministratore.",
            "Esempio: python -m app.cli.create_client my-app my-client-id --scope reports:read",
            err=True,
        )
        raise typer.Exit(code=1)

    normalized_client_id = (client_id or "").strip()
    if not normalized_client_id:
        typer.secho(
            "Errore: devi specificare un client_id scelto dall'amministratore.",
            err=True,
            fg=typer.colors.RED,
        )
        typer.secho(
            "Esempio: python -m app.cli.create_client my-app my-client-id --scope reports:read",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        client, client_secret = create_client_application(
            name=normalized_name,
            client_id=normalized_client_id,
            scopes=scopes or [],
        )
    except ValueError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo("Client creato con successo!")
    typer.echo(f"client_id: {client.client_id}")
    typer.echo(f"client_secret: {client_secret}")
    typer.echo("Conserva il secret in modo sicuro: non verrà mostrato di nuovo.")


if __name__ == "__main__":
    typer.run(create)
