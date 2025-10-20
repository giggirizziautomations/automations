"""Generate and persist a JWT secret."""
from __future__ import annotations

from pathlib import Path
import secrets

import typer


DEFAULT_SECRET_FILE = Path(".jwt.secret")
DEFAULT_NBYTES = 32


def generate(
    output: Path = typer.Option(
        DEFAULT_SECRET_FILE,
        help="File di output per il secret JWT",
    ),
    nbytes: int = typer.Option(
        DEFAULT_NBYTES,
        min=16,
        max=128,
        help="Numero di byte casuali utilizzati per generare il secret",
    ),
) -> None:
    """Generate a random JWT secret and store it on disk."""

    secret = secrets.token_urlsafe(nbytes)
    output.write_text(secret)
    typer.echo(f"Secret JWT generato e salvato in {output}.")
    typer.echo("Imposta l'ambiente con: export JWT_SECRET='" + secret + "'")


if __name__ == "__main__":
    typer.run(generate)
