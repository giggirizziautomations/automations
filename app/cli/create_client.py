"""CLI utility for creating client credential entries."""
from __future__ import annotations

from typing import Optional, Sequence
from typing import Sequence

import click

from app.setup.client_credentials import create_client_application


@click.command()
@click.argument("name")
@click.argument("client_id_argument", required=False)
@click.option(
    "client_id_option",
    "--client-id",
    "-c",
    help="Identificativo client scelto dall'amministratore",
    show_default=False,
)
@click.argument("client_id")
@click.option(
    "scopes",
    "--scope",
    "-s",
    multiple=True,
    help="Scope da assegnare (opzione ripetibile)",
    show_default=False,
)
def create(
    name: str,
    client_id_argument: Optional[str],
    client_id_option: Optional[str],
    scopes: Sequence[str],
) -> None:
def create(name: str, client_id: str, scopes: Sequence[str]) -> None:
    """Create a new client credentials application."""

    normalized_name = name.strip()
    if not normalized_name:
        click.secho(
            "Errore: il nome dell'applicazione client non può essere vuoto.",
            err=True,
            fg="red",
        )
        raise click.Abort()

    normalized_option = (client_id_option or "").strip()
    normalized_argument = (client_id_argument or "").strip()

    if normalized_option and normalized_argument and normalized_option != normalized_argument:
        click.secho(
            "Errore: specifica un unico valore per il client_id (usa --client-id oppure l'argomento posizionale).",
            err=True,
            fg="red",
        )
        raise click.Abort()

    normalized_client_id = normalized_option or normalized_argument
    normalized_client_id = client_id.strip()
    if not normalized_client_id:
        click.secho(
            "Errore: devi specificare un client_id scelto dall'amministratore.",
            err=True,
            fg="red",
        )
        click.secho(
            "Esempio: python -m app.cli.create_client my-app --client-id my-client-id --scope reports:read",
            "Esempio: python -m app.cli.create_client my-app my-client-id --scope reports:read",
            err=True,
            fg="red",
        )
        raise click.Abort()

    try:
        client, client_secret = create_client_application(
            name=normalized_name,
            client_id=normalized_client_id,
            scopes=list(scopes) or [],
        )
    except ValueError as exc:
        click.secho(str(exc), err=True, fg="red")
        raise click.Abort() from exc

    click.echo("Client creato con successo!")
    click.echo(f"client_id: {client.client_id}")
    click.echo(f"client_secret: {client_secret}")
    click.echo("Conserva il secret in modo sicuro: non verrà mostrato di nuovo.")


if __name__ == "__main__":
    create()
