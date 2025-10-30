"""Open a webpage using Playwright from the command line."""
from __future__ import annotations

import asyncio

import typer

from app.core.browser import open_webpage


def launch(
    url: str = typer.Argument(..., help="Address of the page to open"),
    user: str = typer.Argument(..., help="Identifier of the user invoking the command"),
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help=(
            "Identifier of the browser session to use. "
            "Defaults to a per-user session named 'default'."
        ),
    ),
) -> None:
    """Launch a headed browser session to open ``url`` for ``user``."""

    metadata = asyncio.run(open_webpage(url, user, session_id=session_id))
    resolved_session = metadata.get("session_id") or session_id or "default"

    typer.echo(
        "Opened {page} for user {user} (session {session}). Waiting completed for full load.".format(
            page=metadata.get("url", url),
            user=user,
            session=resolved_session,
        )
    )


if __name__ == "__main__":
    typer.run(launch)
