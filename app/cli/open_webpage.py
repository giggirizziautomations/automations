"""Open a webpage using Playwright from the command line."""
from __future__ import annotations

import asyncio

import typer

from app.core.browser import open_webpage


def launch(
    url: str = typer.Argument(..., help="Address of the page to open"),
    user: str = typer.Argument(..., help="Identifier of the user invoking the command"),
) -> None:
    """Launch a headless browser session to open ``url`` for ``user``."""

    asyncio.run(open_webpage(url, user))
    typer.echo(f"Opened {url} for user {user}.")


if __name__ == "__main__":
    typer.run(launch)
