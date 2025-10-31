"""Execute scraping routines against an active Playwright page."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

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


@dataclass
class CustomActionResult:
    """Result returned by a custom action handler."""

    status: str
    detail: str | None = None
    context_updates: dict[str, Any] = field(default_factory=dict)


CustomActionHandler = Callable[
    [ScrapingAction, RoutineCredentials, dict[str, Any]],
    Awaitable[CustomActionResult | None],
]


def _parse_actions(routine: models.ScrapingRoutine) -> list[ScrapingAction]:
    actions_raw = routine.get_actions()
    return [ScrapingAction(**action) for action in actions_raw]


def _lookup_context_value(context: dict[str, Any], key: str) -> Any:
    current: Any = context
    for chunk in key.split("."):
        chunk = chunk.strip()
        if not chunk:
            return None
        if isinstance(current, dict):
            current = current.get(chunk)
        else:
            return None
    return current


def _merge_context(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _merge_context(target[key], value)
        else:
            target[key] = value


def _resolve_input_value(
    action: ScrapingAction,
    credentials: RoutineCredentials,
    context: dict[str, Any],
) -> str | None:
    metadata = action.metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}

    context_key = metadata.get("context_key")
    if isinstance(context_key, str):
        context_value = _lookup_context_value(context, context_key)
        if context_value is not None:
            return str(context_value)

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


def _resolve_select_value(
    action: ScrapingAction,
    credentials: RoutineCredentials,
    context: dict[str, Any],
) -> str | None:
    value = _resolve_input_value(action, credentials, context)
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
    context: dict[str, Any],
    custom_action_handler: CustomActionHandler | None,
) -> dict[str, Any]:
    status = "success"
    detail: str | None = None
    used_input: str | None = None

    try:
        if action.type == "click":
            await page.click(action.selector)
        elif action.type == "fill":
            used_input = _resolve_input_value(action, credentials, context)
            if used_input is None:
                status = "skipped"
                detail = "No value available for fill action"
            else:
                await page.fill(action.selector, used_input)
        elif action.type == "select":
            used_input = _resolve_select_value(action, credentials, context)
            if used_input is None:
                status = "skipped"
                detail = "No option value available for select action"
            else:
                await page.select_option(action.selector, used_input)
        elif action.type == "wait":
            timeout_ms = _resolve_wait_timeout(action)
            await page.wait_for_timeout(timeout_ms)
        else:  # custom or other
            handled = False
            if custom_action_handler is not None:
                custom_result = await custom_action_handler(action, credentials, context)
                if custom_result is not None:
                    status = custom_result.status
                    detail = custom_result.detail
                    updates = custom_result.context_updates or {}
                    if updates:
                        _merge_context(context, updates)
                    handled = True
            if not handled:
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
    custom_action_handler: CustomActionHandler | None = None,
) -> ScrapingExecutionOutcome:
    """Execute ``routine`` using ``page`` and return structured results."""

    actions = _parse_actions(routine)

    if not page.url or page.url == "about:blank":  # pragma: no branch - simple guard
        await page.goto(routine.url, wait_until="networkidle")

    results: list[dict[str, Any]] = []
    context: dict[str, Any] = {}
    for index, action in enumerate(actions):
        result = await _execute_single_action(
            page=page,
            index=index,
            action=action,
            credentials=credentials,
            context=context,
            custom_action_handler=custom_action_handler,
        )
        results.append(result)

    return ScrapingExecutionOutcome(url=page.url, results=results)


__all__ = [
    "PageProtocol",
    "RoutineCredentials",
    "ScrapingExecutionOutcome",
    "execute_scraping_routine",
]
