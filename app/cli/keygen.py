"""Generate and persist a Fernet key."""
from __future__ import annotations

from pathlib import Path

import typer
from cryptography.fernet import Fernet

from .utils import upsert_env_value


def generate(
    env_file: Path = typer.Option(
        Path(".env"),
        exists=False,
        dir_okay=False,
        writable=True,
        help="File .env da aggiornare con la chiave generata",
    ),
) -> None:
    """Generate a new Fernet key and store it inside the env file."""

    key = Fernet.generate_key().decode()
    upsert_env_value(env_file, "FERNET_KEY", key)
    typer.echo(
        f"Chiave Fernet generata e salvata in {env_file} (variabile FERNET_KEY).",
    )


if __name__ == "__main__":
    typer.run(generate)
