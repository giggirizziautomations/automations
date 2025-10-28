"""Execute scraping routines against an active Playwright page."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.db import models
from app.schemas.scraping import ScrapingAction


logger = logging.getLogger(__name__)


class PageProtocol(Protocol):
    """Protocol describing the subset of Playwright's page API we use."""

    @property
    def url(self) -> str:  # pragma: no cover - property delegation
        """Return the current URL displayed by the page."""

    async def goto(self, url: str, *, wait_until: str = "networkidle") -> Any:
        ...

    async def click(self, selector: str) -> Any:
        ...

    async def fill(self, selector: str, value: str) -> Any:
        ...

    async def select_option(self, selector: str, value: str) -> Any:
        ...

    async def wait_for_timeout(self, timeout: float) -> Any:
        ...

    async def evaluate(self, expression: str) -> Any:
        ...


@dataclass
class RoutineCredentials:
    """Resolved credentials available to a scraping routine."""

    email: str
    password: str


@dataclass
class ScrapingExecutionOutcome:
    """Outcome of executing a scraping routine."""

    url: str
    results: list[dict[str, Any]]


def _parse_actions(routine: models.ScrapingRoutine) -> list[ScrapingAction]:
    actions_raw = routine.get_actions()
    return [ScrapingAction(**action) for action in actions_raw]


def _resolve_input_value(action: ScrapingAction, credentials: RoutineCredentials) -> str | None:
    metadata = action.metadata or {}
    attributes = metadata.get("attributes", {}) if isinstance(metadata, dict) else {}

    if action.input_text:
        return action.input_text

    if metadata.get("expects_secret"):
        return credentials.password

    label = str(metadata.get("label") or "").lower() if isinstance(metadata, dict) else ""
    if "password" in label:
        return credentials.password
    if "email" in label:
        return credentials.email

    attr_type = str(attributes.get("type") or "").lower()
    if attr_type == "password":
        return credentials.password
    for key in ("name", "id", "data-testid", "aria-label", "placeholder"):
        value = attributes.get(key)
        if isinstance(value, str):
            lowered = value.lower()
            if "email" in lowered and attr_type in {"", "text", "email"}:
                return credentials.email
            if any(token in lowered for token in ("pass", "pwd")):
                return credentials.password
    if attr_type == "email":
        return credentials.email

    suggested = metadata.get("suggested_value") if isinstance(metadata, dict) else None
    if suggested:
        return str(suggested)

    return None


def _resolve_select_value(action: ScrapingAction, credentials: RoutineCredentials) -> str | None:
    value = _resolve_input_value(action, credentials)
    if value is not None:
        return value

    metadata = action.metadata or {}
    if isinstance(metadata, dict):
        selected = metadata.get("selected_option")
        if isinstance(selected, str) and selected:
            return selected

    return None


def _resolve_wait_timeout(action: ScrapingAction) -> float:
    metadata = action.metadata or {}
    if isinstance(metadata, dict):
        delay = metadata.get("delay_seconds")
        if isinstance(delay, (int, float)) and delay >= 0:
            return float(delay) * 1000
    return 1000.0


async def _execute_single_action(
    *,
    page: PageProtocol,
    index: int,
    action: ScrapingAction,
    credentials: RoutineCredentials,
) -> dict[str, Any]:
    status = "success"
    detail: str | None = None
    used_input: str | None = None

    try:
        if action.type == "click":
            await page.click(action.selector)
        elif action.type == "fill":
            used_input = _resolve_input_value(action, credentials)
            if used_input is None:
                status = "skipped"
                detail = "No value available for fill action"
            else:
                await page.fill(action.selector, used_input)
        elif action.type == "select":
            used_input = _resolve_select_value(action, credentials)
            if used_input is None:
                status = "skipped"
                detail = "No option value available for select action"
            else:
                await page.select_option(action.selector, used_input)
        elif action.type == "wait":
            timeout_ms = _resolve_wait_timeout(action)
            await page.wait_for_timeout(timeout_ms)
        else:  # custom or other
            metadata = action.metadata or {}
            script = metadata.get("script") if isinstance(metadata, dict) else None
            if script:
                await page.evaluate(script)
            else:
                status = "skipped"
                detail = "No executable script provided"
    except Exception as exc:  # pragma: no cover - exercised via tests with fakes
        logger.exception("Failed to execute action %s at index %s", action.type, index)
        status = "error"
        detail = str(exc)

    return {
        "index": index,
        "type": action.type,
        "selector": action.selector,
        "status": status,
        "detail": detail,
        "input_text": used_input,
    }


async def execute_scraping_routine(
    *,
    routine: models.ScrapingRoutine,
    page: PageProtocol,
    credentials: RoutineCredentials,
) -> ScrapingExecutionOutcome:
    """Execute ``routine`` using ``page`` and return structured results."""

    actions = _parse_actions(routine)

    if not page.url or page.url == "about:blank":  # pragma: no branch - simple guard
        await page.goto(routine.url, wait_until="networkidle")

    results: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        result = await _execute_single_action(
            page=page,
            index=index,
            action=action,
            credentials=credentials,
        )
        results.append(result)

    return ScrapingExecutionOutcome(url=page.url, results=results)


__all__ = [
    "PageProtocol",
    "RoutineCredentials",
    "ScrapingExecutionOutcome",
    "execute_scraping_routine",
]
