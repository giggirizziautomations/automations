"""Utilities for working with JSON payloads."""
from __future__ import annotations

from typing import Any

import json


def _escape_html_snippet_field(data: str) -> str:
    """Escape unescaped double quotes inside the ``html_snippet`` field.

    Some clients submit HTML fragments that contain double quotes without
    escaping them for JSON (e.g. ``data-bind="text: value"``). The FastAPI JSON
    decoder rejects these payloads, so we detect the ``html_snippet`` field and
    escape interior quotes while leaving the terminating quote untouched.
    """

    marker = '"html_snippet": "'
    start = data.find(marker)
    if start == -1:
        return data

    # Convert to a list for easier in-place manipulation.
    chars = list(data)
    index = start + len(marker)
    while index < len(chars):
        char = chars[index]
        if char == '"':
            # Look ahead to determine whether this quote terminates the value.
            lookahead = index + 1
            while lookahead < len(chars) and chars[lookahead].isspace():
                lookahead += 1

            if lookahead >= len(chars):
                # We reached the end of the payload. Escape the quote and exit.
                chars.insert(index, "\\")
                break

            if chars[lookahead] in ",}]":
                # The quote terminates the JSON string value; keep it as-is.
                break

            # This is an interior quote belonging to the HTML snippet. Escape it
            # so that ``json.loads`` accepts the payload.
            chars.insert(index, "\\")
            index += 1
        index += 1

    return "".join(chars)


def relaxed_json_loads(data: str, /) -> Any:
    """Lenient JSON loader that tolerates raw HTML snippets.

    The loader first attempts to parse the payload using ``json.loads``. When
    decoding fails we try to sanitise the ``html_snippet`` field by escaping
    problematic quotes before retrying.
    """

    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        patched = _escape_html_snippet_field(data)
        if patched == data:
            raise
        return json.loads(patched)  # May still raise JSONDecodeError.


__all__ = ["relaxed_json_loads"]
