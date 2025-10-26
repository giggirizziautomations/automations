"""Reusable scraping actions and composition helpers for scraping jobs."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from copy import deepcopy
from typing import Any, TypedDict

from playwright.async_api import Page


class ScrapingResult(TypedDict, total=False):
    """Structure used to return scraping results."""

    title: str
    current_url: str
    notes: str
    snapshot_path: str
    metadata: dict[str, Any]


class ActionStep(TypedDict, total=False):
    """High-level description of a scraping step chosen by the user."""

    action: str
    selector: str
    text: str
    attribute: str
    store_as: str
    key: str
    milliseconds: int
    seconds: float
    timeout_ms: int
    state: str
    button: str
    clicks: int
    click_count: int
    delay_ms: int
    x: int
    y: int
    offset: int
    path: str
    full_page: bool
    length_only: bool
    value: str


ScrapingAction = Callable[[Page, dict[str, Any], ScrapingResult], Awaitable[None]]


class ActionDefinition(TypedDict):
    """Information about an action including handler and documentation."""

    handler: ScrapingAction
    description: str
    required_fields: tuple[str, ...]
    optional_fields: dict[str, str]
ScrapingRecipe = Callable[[Page, dict[str, Any]], Awaitable[ScrapingResult]]


def _get_metadata_bucket(result: ScrapingResult) -> dict[str, Any]:
    metadata = result.get("metadata")
    if metadata is None:
        metadata = {}
        result["metadata"] = metadata
    return metadata


async def wait_action(page: Page, params: dict[str, Any], _: ScrapingResult
) -> None:
    """Pause execution for the requested amount of milliseconds."""

    seconds = params.get("seconds")
    if seconds is not None:
        timeout = int(float(seconds) * 1000)
    else:
        timeout = int(params.get("milliseconds", params.get("timeout_ms", 1000)))

    if timeout > 0:
        await page.wait_for_timeout(timeout)


async def wait_for_selector_action(
    page: Page, params: dict[str, Any], _: ScrapingResult
) -> None:
    """Block until ``selector`` becomes available."""

    selector = params["selector"]
    await page.wait_for_selector(
        selector,
        state=params.get("state", "visible"),
        timeout=params.get("timeout_ms"),
    )


async def click_action(page: Page, params: dict[str, Any], _: ScrapingResult) -> None:
    """Click the element matching ``selector``."""

    await page.click(
        params["selector"],
        button=params.get("button", "left"),
        click_count=params.get("click_count", params.get("clicks", 1)),
        delay=params.get("delay_ms"),
        timeout=params.get("timeout_ms"),
    )


async def fill_action(page: Page, params: dict[str, Any], _: ScrapingResult) -> None:
    """Fill the input located at ``selector`` with ``value``."""

    await page.fill(
        params["selector"],
        params.get("value", params.get("text", "")),
        timeout=params.get("timeout_ms"),
    )


async def hover_action(page: Page, params: dict[str, Any], _: ScrapingResult) -> None:
    """Hover over the element matching ``selector``."""

    await page.hover(
        params["selector"],
        timeout=params.get("timeout_ms"),
    )


async def scroll_action(page: Page, params: dict[str, Any], _: ScrapingResult) -> None:
    """Scroll the page to the required ``y`` offset."""

    x = params.get("x", 0)
    y = params.get("y", params.get("offset", 0))
    await page.evaluate("window.scrollTo(arguments[0], arguments[1])", x, y)


async def extract_text_action(
    page: Page, params: dict[str, Any], result: ScrapingResult
) -> None:
    """Store the text content of ``selector`` under ``key``."""

    key = params.get("key") or params.get("store_as") or params["selector"]
    locator = page.locator(params["selector"])
    text = await locator.inner_text(timeout=params.get("timeout_ms"))
    metadata = _get_metadata_bucket(result)
    metadata[key] = text


async def extract_attribute_action(
    page: Page, params: dict[str, Any], result: ScrapingResult
) -> None:
    """Store the attribute value from ``selector`` under ``key``."""

    key = params.get("key") or params.get("store_as") or params["attribute"]
    locator = page.locator(params["selector"])
    value = await locator.get_attribute(
        params["attribute"],
        timeout=params.get("timeout_ms"),
    )
    metadata = _get_metadata_bucket(result)
    metadata[key] = value


async def collect_html_action(
    page: Page, params: dict[str, Any], result: ScrapingResult
) -> None:
    """Capture the HTML content (or its length) for auditing."""

    capture_key = params.get("key") or params.get("store_as", "html")
    html = await page.content()
    metadata = _get_metadata_bucket(result)
    if params.get("length_only", False):
        metadata[f"{capture_key}_length"] = len(html)
    else:
        metadata[capture_key] = html


async def screenshot_action(
    page: Page, params: dict[str, Any], result: ScrapingResult
) -> None:
    """Take a screenshot of the current page and store its path."""

    path = params.get("path", "screenshot.png")
    await page.screenshot(path=path, full_page=params.get("full_page", True))
    result["snapshot_path"] = path


SCRAPING_ACTIONS: dict[str, ActionDefinition] = {
    "wait": {
        "handler": wait_action,
        "description": "Pause the flow for a fixed amount of time.",
        "required_fields": (),
        "optional_fields": {
            "milliseconds": "Number of milliseconds to wait (default 1000).",
            "seconds": "Seconds to wait; overrides milliseconds when provided.",
            "timeout_ms": "Alias for milliseconds kept for backwards compatibility.",
        },
    },
    "wait_for_element": {
        "handler": wait_for_selector_action,
        "description": "Wait until a page element is in the desired state.",
        "required_fields": ("selector",),
        "optional_fields": {
            "state": "State to wait for (visible, attached, detached, hidden).",
            "timeout_ms": "Maximum time to wait before failing (milliseconds).",
        },
    },
    "click": {
        "handler": click_action,
        "description": "Click a button or link identified by a selector.",
        "required_fields": ("selector",),
        "optional_fields": {
            "button": "Which mouse button to use (left, right, middle).",
            "clicks": "How many times to click (default 1).",
            "click_count": "Alias for clicks.",
            "delay_ms": "Delay between clicks in milliseconds.",
            "timeout_ms": "Maximum wait for the element to be ready.",
        },
    },
    "fill": {
        "handler": fill_action,
        "description": "Fill a form field with some text.",
        "required_fields": ("selector",),
        "optional_fields": {
            "text": "Text to write into the field.",
            "value": "Alternative field for text.",
            "timeout_ms": "Maximum wait for the element to be ready.",
        },
    },
    "hover": {
        "handler": hover_action,
        "description": "Move the mouse over a selector.",
        "required_fields": ("selector",),
        "optional_fields": {
            "timeout_ms": "Maximum wait for the element to be ready.",
        },
    },
    "scroll_to": {
        "handler": scroll_action,
        "description": "Scroll the page to specific coordinates.",
        "required_fields": (),
        "optional_fields": {
            "x": "Horizontal scroll offset.",
            "y": "Vertical scroll offset.",
            "offset": "Alias for y, useful for quick vertical scrolling.",
        },
    },
    "get_text": {
        "handler": extract_text_action,
        "description": "Capture the text content of an element and store it.",
        "required_fields": ("selector",),
        "optional_fields": {
            "store_as": "Key name to store the extracted text under.",
            "key": "Alias for store_as.",
            "timeout_ms": "Maximum wait for the element to be ready.",
        },
    },
    "get_attribute": {
        "handler": extract_attribute_action,
        "description": "Capture the value of an element attribute.",
        "required_fields": ("selector", "attribute"),
        "optional_fields": {
            "store_as": "Key name to store the extracted value under.",
            "key": "Alias for store_as.",
            "timeout_ms": "Maximum wait for the element to be ready.",
        },
    },
    "save_html": {
        "handler": collect_html_action,
        "description": "Store the full HTML markup of the current page.",
        "required_fields": (),
        "optional_fields": {
            "store_as": "Key name for the saved HTML (default 'html').",
            "key": "Alias for store_as.",
            "length_only": "If true, store the HTML length instead of the markup.",
        },
    },
    "screenshot": {
        "handler": screenshot_action,
        "description": "Capture a screenshot of the current page.",
        "required_fields": (),
        "optional_fields": {
            "path": "Filename where the screenshot will be saved.",
            "full_page": "Capture the full page instead of the viewport (default True).",
        },
    },
}


def _coerce_action_step(raw_step: Mapping[str, Any] | ActionStep) -> tuple[str, dict[str, Any]]:
    """Return the action name and a normalized parameters mapping."""

    data = dict(raw_step)

    name = data.pop("action", None) or data.pop("name", None)
    if name is None:
        raise KeyError("Action is missing the 'action' field")

    params: dict[str, Any] = {}
    if "params" in data:
        raw_params = data.pop("params")
        if not isinstance(raw_params, Mapping):  # pragma: no cover - defensive path
            raise TypeError("The 'params' entry must be a mapping")
        params.update(raw_params)
    params.update(data)
    return name, params


def _infer_credential_key(params: Mapping[str, Any]) -> str | None:
    """Guess whether ``params`` reference the email or password field."""

    explicit = str(params.get("use") or params.get("credential") or "").strip().lower()
    if explicit in {"email", "username"}:
        return "email"
    if explicit in {"password", "passcode", "pwd"}:
        return "password"

    selector = str(params.get("selector") or "").lower()
    field_name = str(params.get("field") or params.get("name") or "").lower()

    haystack = " ".join(part for part in (selector, field_name) if part)

    password_tokens = ("password", "passwd", "passcode", "pwd")
    if any(token in haystack for token in password_tokens):
        return "password"

    email_tokens = ("email", "username", "user", "login")
    if any(token in haystack for token in email_tokens):
        return "email"

    return None


def _hydrate_action_parameters(
    name: str,
    params: dict[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Ensure missing credential values are populated from ``context``."""

    if name != "fill":
        return params

    value = params.get("value")
    text = params.get("text")
    if value not in (None, "") or text not in (None, ""):
        return params

    credential_key = _infer_credential_key(params)
    if not credential_key:
        return params

    credential_value = context.get(credential_key)
    if credential_value is None:
        return params

    enriched = dict(params)
    enriched.setdefault("value", credential_value)
    if not enriched.get("text"):
        enriched["text"] = credential_value
    return enriched


async def execute_actions(
    page: Page,
    actions: Iterable[Mapping[str, Any] | ActionStep],
    result: ScrapingResult,
    *,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Execute ``actions`` sequentially, mutating ``result`` in-place."""

    for idx, action_spec in enumerate(actions, start=1):
        if not isinstance(action_spec, Mapping):  # pragma: no cover - defensive path
            raise TypeError("Each action entry must be a mapping")

        try:
            name, params = _coerce_action_step(action_spec)
        except KeyError as exc:  # pragma: no cover - defensive path
            raise KeyError(f"Action specification #{idx} is missing 'action'") from exc

        try:
            definition = SCRAPING_ACTIONS[name]
        except KeyError as exc:  # pragma: no cover - defensive path
            raise KeyError(
                f"Unknown scraping action: {name}. Available actions: {', '.join(sorted(SCRAPING_ACTIONS))}"
            ) from exc

        params = _hydrate_action_parameters(name, params, context or {})

        missing = [field for field in definition["required_fields"] if field not in params]
        if missing:
            raise KeyError(
                f"Action '{name}' is missing required fields: {', '.join(missing)}"
            )

        await definition["handler"](page, params, result)


async def default_recipe(page: Page, parameters: dict[str, Any]) -> ScrapingResult:
    """Collect basic metadata from the current page and optional actions."""

    settle_ms = int(parameters.get("settle_ms", 1000))
    if settle_ms > 0:
        await page.wait_for_timeout(settle_ms)

    result: ScrapingResult = {
        "title": await page.title(),
        "current_url": page.url,
    }

    actions_param = parameters.get("actions")
    if actions_param:
        if isinstance(actions_param, dict):
            actions = [actions_param]
        elif isinstance(actions_param, (list, tuple)):
            actions = actions_param
        else:  # pragma: no cover - defensive path
            raise TypeError(
                "The 'actions' parameter must be a mapping or a list/tuple of mappings"
            )
        await execute_actions(page, actions, result, context=parameters)

    return result


async def save_screenshot_recipe(page: Page, parameters: dict[str, Any]) -> ScrapingResult:
    """Ensure a screenshot action is executed after any user-provided actions."""

    all_params = deepcopy(parameters)
    actions = list(all_params.get("actions", []))
    actions.append({
        "action": "screenshot",
        "path": all_params.get("path", "screenshot.png"),
        "full_page": True,
    })
    all_params["actions"] = actions
    return await default_recipe(page, all_params)


RECIPES: dict[str, ScrapingRecipe] = {
    "default": default_recipe,
    "save_screenshot": save_screenshot_recipe,
}


__all__ = [
    "ActionDefinition",
    "ActionStep",
    "ScrapingAction",
    "SCRAPING_ACTIONS",
    "RECIPES",
    "ScrapingRecipe",
    "ScrapingResult",
    "collect_html_action",
    "default_recipe",
    "execute_actions",
    "extract_attribute_action",
    "extract_text_action",
    "fill_action",
    "hover_action",
    "save_screenshot_recipe",
    "screenshot_action",
    "scroll_action",
    "wait_action",
    "wait_for_selector_action",
    "click_action",
]
