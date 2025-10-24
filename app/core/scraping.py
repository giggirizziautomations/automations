"""High-level orchestration helpers for scraping sessions."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.browser import _launch_browser, _shutdown_browser
from app.db.models import ScrapingTarget, User
from app.scraping.recipes import RECIPES, ScrapingRecipe

logger = logging.getLogger(__name__)


class ScrapingConfigurationError(RuntimeError):
    """Raised when the scraping configuration cannot be resolved."""


def load_target(session: Session, *, user_id: int, site_name: str) -> ScrapingTarget:
    """Return the scraping target for ``user_id`` and ``site_name``.

    The function raises :class:`ScrapingConfigurationError` if no matching
    configuration is found in the database.
    """

    stmt = (
        select(ScrapingTarget)
        .join(ScrapingTarget.user)
        .where(User.id == user_id, ScrapingTarget.site_name == site_name)
    )
    result = session.execute(stmt).scalars().first()
    if result is None:
        raise ScrapingConfigurationError(
            "No scraping configuration found for user_id=%s and site=%s" % (user_id, site_name)
        )
    return result


def _resolve_recipe(target: ScrapingTarget) -> ScrapingRecipe:
    recipe_name = (target.recipe or "default").strip() or "default"
    try:
        return RECIPES[recipe_name]
    except KeyError as exc:  # pragma: no cover - defensive path
        raise ScrapingConfigurationError(
            "Recipe %r is not registered. Available options: %s"
            % (recipe_name, ", ".join(sorted(RECIPES)))
        ) from exc


def _parse_parameters(raw: str | Mapping[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover - defensive path
        raise ScrapingConfigurationError("Invalid JSON parameters: %s" % raw) from exc


async def execute_scraping(
    target: ScrapingTarget,
    *,
    invoked_by: str | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Execute a scraping job defined by ``target``.

    Parameters
    ----------
    target:
        Database entry describing how to reach the target website.
    invoked_by:
        Optional identifier for the user launching the operation. When omitted
        the system will use the e-mail address of the associated user.
    headless:
        If ``True`` the browser will run in headless mode.
    """

    owner_label: str
    if target.user and target.user.email:
        owner_label = target.user.email
    else:
        owner_label = f"user-{target.user_id}"

    runner_label = (invoked_by or "").strip() or owner_label

    recipe = _resolve_recipe(target)
    parameters = _parse_parameters(target.parameters)

    logger.info(
        "Starting scraping for user %s on %s (%s) using recipe %s",
        runner_label,
        target.site_name,
        target.url,
        recipe.__name__,
    )

    playwright, browser = await _launch_browser(headless=headless)
    page = await browser.new_page()
    try:
        await page.goto(target.url, wait_until="networkidle")
        result = await recipe(page, parameters)
    except Exception:
        logger.exception("Scraping failed for user %s on site %s", runner_label, target.site_name)
        raise
    finally:
        await _shutdown_browser(playwright, browser)

    payload: dict[str, Any] = {
        "status": "completed",
        "site": target.site_name,
        "url": target.url,
        "user": owner_label,
        "run_by": runner_label,
        "recipe": target.recipe or "default",
        "data": result,
    }

    logger.info(
        "Finished scraping for user %s on %s (%s)",
        runner_label,
        target.site_name,
        target.url,
    )
    return payload


def run_scraping_job(
    session: Session,
    *,
    site_name: str,
    user_id: int,
    headless: bool = True,
    invoked_by: str | None = None,
) -> dict[str, Any]:
    """Synchronously execute a scraping job using the current event loop."""

    target = load_target(session, user_id=user_id, site_name=site_name)
    return asyncio.run(
        execute_scraping(target, invoked_by=invoked_by, headless=headless)
    )


__all__ = [
    "ScrapingConfigurationError",
    "execute_scraping",
    "load_target",
    "run_scraping_job",
]
