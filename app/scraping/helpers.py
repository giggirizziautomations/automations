"""Utilities to build scraping action payloads from HTML snippets."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from app.scraping.recipes import ActionStep


@dataclass
class _ElementDescription:
    """Simple container describing the first HTML element in a snippet."""

    tag: str | None = None
    attributes: dict[str, str] | None = None

    @property
    def has_data(self) -> bool:
        return bool(self.tag)


class _ElementSniffer(HTMLParser):
    """Capture the first element (tag + attributes) from an HTML snippet."""

    def __init__(self) -> None:
        super().__init__()
        self.description = _ElementDescription()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: D401
        self._record(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: D401
        self._record(tag, attrs)

    def _record(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.description.tag is not None:
            return
        self.description = _ElementDescription(
            tag=tag,
            attributes={name: value or "" for name, value in attrs},
        )


def _build_selector(element: _ElementDescription) -> str:
    """Return a CSS selector targeting ``element`` as precisely as possible."""

    if not element.has_data:
        return "body"

    attributes = element.attributes or {}
    tag = element.tag or "div"

    element_id = attributes.get("id")
    if element_id:
        return f"#{element_id}"

    class_names = attributes.get("class", "").split()
    if class_names:
        classes = "".join(f".{cls}" for cls in class_names if cls)
        return f"{tag}{classes}"

    for attr_name in ("name", "data-testid", "data-test", "data-qa", "aria-label"):
        attr_value = attributes.get(attr_name)
        if attr_value:
            return f'{tag}[{attr_name}="{attr_value}"]'

    type_attr = attributes.get("type")
    if type_attr:
        return f'{tag}[type="{type_attr}"]'

    return tag


def _normalise_suggestion(value: str) -> str:
    return value.strip().lower()


def _resolve_fill_value(attributes: dict[str, str], explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for candidate in ("value", "placeholder", "aria-label", "title"):
        inferred = attributes.get(candidate)
        if inferred:
            return inferred
    return None


def build_action_step(
    html_snippet: str,
    suggestion: str,
    *,
    value: str | None = None,
) -> ActionStep:
    """Return a single scraping action inferred from ``html_snippet`` and ``suggestion``.

    Parameters
    ----------
    html_snippet:
        Raw HTML describing the element the automation should target.
    suggestion:
        High-level instruction such as ``"wait"``, ``"click"`` or ``"input text"``.
    value:
        Optional text to use when the action requires a value (for example when
        filling an input field).
    """

    parser = _ElementSniffer()
    parser.feed(html_snippet)
    element = parser.description

    suggestion_key = _normalise_suggestion(suggestion)
    selector = _build_selector(element)
    attributes = element.attributes or {}

    if suggestion_key in {"wait", "wait for element", "wait for selector"}:
        if element.has_data:
            return {"action": "wait_for_element", "selector": selector, "state": "visible"}
        return {"action": "wait", "milliseconds": 1000}

    if suggestion_key in {"click", "press", "tap"}:
        if not element.has_data:
            raise ValueError("Cannot infer a selector for the requested click action")
        return {"action": "click", "selector": selector}

    if suggestion_key in {"input", "input text", "fill", "type", "type text"}:
        if not element.has_data:
            raise ValueError("Cannot infer a selector for the requested input action")
        fill_value = _resolve_fill_value(attributes, value)
        action: ActionStep = {"action": "fill", "selector": selector}
        if fill_value is not None:
            action["value"] = fill_value
        return action

    raise ValueError(f"Unsupported suggestion: {suggestion}")


def build_actions_document(
    html_snippet: str,
    suggestion: str,
    *,
    value: str | None = None,
    settle_ms: int | None = None,
) -> dict[str, Any]:
    """Return a JSON-serialisable document ready to be stored as parameters."""

    action = build_action_step(html_snippet, suggestion, value=value)
    document: dict[str, Any] = {"actions": [action]}
    if settle_ms is not None:
        document["settle_ms"] = settle_ms
    return document


__all__ = ["build_action_step", "build_actions_document"]

