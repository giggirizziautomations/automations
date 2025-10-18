"""Generate and persist a Fernet key."""
from __future__ import annotations

from pathlib import Path

import typer
from cryptography.fernet import Fernet


def generate(
    output: Path = typer.Option(Path(".fernet.key"), help="File di output per la chiave"),
) -> None:
    """Generate a new Fernet key and store it on disk."""

    key = Fernet.generate_key()
    output.write_bytes(key)
    typer.echo(f"Chiave Fernet generata e salvata in {output}.")
    typer.echo("Imposta l'ambiente con: export FERNET_KEY='" + key.decode() + "'")


if __name__ == "__main__":
    typer.run(generate)
