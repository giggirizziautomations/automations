"""CLI entry point to launch scraping jobs configured in the database."""
from __future__ import annotations

import json
import sys
from contextlib import suppress
from pathlib import Path

import typer
from sqlalchemy.orm import Session

from app.core.scraping import ScrapingConfigurationError, run_scraping_job
from app.db.base import get_sessionmaker


def _open_session() -> Session:
    SessionLocal = get_sessionmaker()
    return SessionLocal()


def launch(
    site_name: str = typer.Argument(..., help="Identifier of the site to scrape"),
    user_id: int = typer.Argument(..., help="User ID owning the configuration"),
    headless: bool = typer.Option(True, help="Run browser in headless mode"),
    invoked_by: str | None = typer.Option(
        None,
        "--invoked-by",
        "-i",
        help=(
            "Optional identifier of the operator launching the scraping job. "
            "When omitted the configuration owner is used."
        ),
    ),
    output: Path | None = typer.Option(None, help="Optional path where to save the JSON report"),
) -> None:
    """Run the scraping job identified by ``site_name`` for ``user_id``."""

    try:
        with _open_session() as session:
            result = run_scraping_job(
                session,
                site_name=site_name,
                user_id=user_id,
                headless=headless,
                invoked_by=invoked_by,
            )
    except ScrapingConfigurationError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover - runtime safety
        typer.secho(f"Scraping failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from exc

    payload = json.dumps(result, indent=2)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Report saved to {output}")
    else:
        typer.echo(payload)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    with suppress(KeyboardInterrupt):
        typer.run(launch)
        sys.exit(0)
