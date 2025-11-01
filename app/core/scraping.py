"""Utility helpers for translating natural language scraping instructions."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Tuple


_ACTION_KEYWORDS: list[tuple[str, str]] = [
    ("click", "click"),
    ("press", "click"),
    ("tap", "click"),
    ("submit", "click"),
    ("choose", "select"),
    ("select", "select"),
    ("pick", "select"),
    ("fill", "fill"),
    ("enter", "fill"),
    ("type", "fill"),
    ("update", "fill"),
    ("write", "fill"),
    ("wait", "wait"),
    ("pause", "wait"),
    ("delay", "wait"),
]

_LABEL_ATTRIBUTES: tuple[str, ...] = (
    "aria-label",
    "placeholder",
    "title",
    "alt",
    "data-testid",
    "data-test",
)


def _normalise_whitespace(value: str) -> str:
    return " ".join(value.split())


def _detect_action_type(instruction: str) -> str:
    text = instruction.lower()
    for keyword, action_type in _ACTION_KEYWORDS:
        if keyword in text:
            return action_type
    return "custom"


def _extract_attributes(html_snippet: str) -> Tuple[str | None, Dict[str, str]]:
    tag_match = re.search(r"<\s*([a-zA-Z0-9:_-]+)", html_snippet)
    tag = tag_match.group(1).lower() if tag_match else None

    attributes: Dict[str, str] = {}
    for attr_match in re.finditer(
        r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*\"([^\"]*)\"|([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*'([^']*)'",
        html_snippet,
    ):
        key = attr_match.group(1) or attr_match.group(3)
        value = attr_match.group(2) or attr_match.group(4) or ""
        attributes[key] = value

    return tag, attributes


def _guess_selector(tag: str | None, attributes: Dict[str, str]) -> str:
    if attributes.get("id"):
        return f"#{attributes['id']}"

    data_attr = next(
        (
            (key, value)
            for key, value in attributes.items()
            if key.startswith("data-") and value
        ),
        None,
    )
    if data_attr:
        key, value = data_attr
        return f"[{key}='{value}']"

    if attributes.get("name") and tag:
        return f"{tag}[name='{attributes['name']}']"

    class_value = attributes.get("class")
    if class_value:
        first_class = class_value.split()[0]
        return f".{first_class}"

    return tag or "*"


def _extract_text(html_snippet: str) -> str | None:
    match = re.search(r">([^<]+)<", html_snippet)
    if not match:
        return None
    text = match.group(1).strip()
    return text or None


def _extract_input_text(instruction: str) -> str | None:
    quotes = re.findall(r"\"([^\"]+)\"|'([^']+)'", instruction)
    if not quotes:
        return None
    for group in quotes:
        for candidate in group:
            if candidate:
                return candidate
    return None


def _extract_label(attributes: Dict[str, str]) -> str | None:
    for key in _LABEL_ATTRIBUTES:
        value = attributes.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _extract_suggested_value(attributes: Dict[str, str]) -> str | None:
    for key in ("value", "placeholder", "data-default", "data-value"):
        value = attributes.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _extract_wait_duration(instruction: str) -> float | None:
    pattern = re.compile(
        r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>milliseconds?|ms|seconds?|secs?|s|minutes?|mins?|m)",
        re.IGNORECASE,
    )
    match = pattern.search(instruction)
    if not match:
        return None

    value = float(match.group("value"))
    unit = match.group("unit").lower()
    if unit.startswith("ms") or unit.startswith("millisecond"):
        return value / 1000
    if unit.startswith("m") and not unit.startswith("ms"):
        return value * 60
    return value


def _calculate_confidence(selector: str, attributes: Dict[str, str]) -> float:
    if selector.startswith("#"):
        return 0.95
    if selector.startswith("[data-"):
        return 0.9
    if selector.startswith("."):
        classes = attributes.get("class", "").split()
        return 0.75 if len(classes) <= 1 else 0.65
    if selector != "*" and selector:
        return 0.55
    return 0.35


def _ensure_metadata_fields(metadata: Dict[str, Any], *, keys: Iterable[str]) -> None:
    for key in keys:
        metadata.setdefault(key, None)


def generate_scraping_action(
    instruction: str, html_snippet: str, store_text_as: str | None = None
) -> Dict[str, Any]:
    """Create a structured scraping action from natural language instructions."""

    instruction = _normalise_whitespace(instruction.strip())
    html_snippet = html_snippet.strip()

    action_type = _detect_action_type(instruction)
    tag, attributes = _extract_attributes(html_snippet)
    selector = _guess_selector(tag, attributes)
    text_content = _extract_text(html_snippet)
    input_text = (
        _extract_input_text(instruction)
        if action_type in {"fill", "select"}
        else None
    )

    metadata: Dict[str, Any] = {
        "attributes": attributes,
        "html_preview": html_snippet,
        "raw_instruction": instruction,
        "confidence": _calculate_confidence(selector, attributes),
    }

    label = _extract_label(attributes)
    if label:
        metadata["label"] = label
    if text_content:
        metadata["text"] = text_content

    suggested_value = _extract_suggested_value(attributes)
    if suggested_value and action_type in {"fill", "select"} and not input_text:
        metadata["suggested_value"] = suggested_value

    if action_type == "wait":
        duration = _extract_wait_duration(instruction)
        if duration is not None:
            metadata["delay_seconds"] = duration

    if action_type == "fill" and attributes.get("type", "").lower() == "password":
        metadata["expects_secret"] = True

    if isinstance(store_text_as, str):
        trimmed_store_key = store_text_as.strip()
        if trimmed_store_key:
            metadata["store_text_as"] = trimmed_store_key

    action: Dict[str, Any] = {
        "type": action_type,
        "selector": selector,
        "description": instruction,
        "target_tag": tag,
        "metadata": metadata,
    }

    if input_text:
        action["input_text"] = input_text

    # Keep the metadata shape stable for downstream consumers by ensuring
    # frequently accessed optional keys exist even when absent in the snippet.
    _ensure_metadata_fields(
        metadata,
        keys=("label", "text", "suggested_value", "delay_seconds"),
    )

    return action


__all__ = ["generate_scraping_action"]
