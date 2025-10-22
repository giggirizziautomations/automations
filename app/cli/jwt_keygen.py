"""Generate and persist a JWT secret."""
from __future__ import annotations

from pathlib import Path
import secrets

import typer


from .utils import upsert_env_value


DEFAULT_ENV_FILE = Path(".env")
DEFAULT_NBYTES = 32


def generate(
    env_file: Path = typer.Option(
        DEFAULT_ENV_FILE,
        exists=False,
        dir_okay=False,
        writable=True,
        help="File .env da aggiornare con il secret JWT",
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
    upsert_env_value(env_file, "JWT_SECRET", secret)
    typer.echo(
        f"Secret JWT generato e salvato in {env_file} (variabile JWT_SECRET).",
    )


if __name__ == "__main__":
    typer.run(generate)
