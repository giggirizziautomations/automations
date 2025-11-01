"""Utilities for working with JSON payloads."""
from __future__ import annotations

from typing import Any

import json


def _escape_html_snippet_field(data: str) -> str:
    """Normalise the ``html_snippet`` field so the payload is valid JSON.

    A number of clients submit HTML fragments that contain raw double quotes and
    literal line breaks. Both are invalid inside JSON strings, so we sanitise the
    ``html_snippet`` value by escaping interior quotes and replacing unescaped
    newlines before handing the payload to :func:`json.loads`.
    """

    marker = '"html_snippet": "'
    start = data.find(marker)
    if start == -1:
        return data

    prefix_end = start + len(marker)
    result: list[str] = [data[:prefix_end]]
    index = prefix_end
    length = len(data)

    while index < length:
        char = data[index]

        if char == "\\":
            # Preserve existing escape sequences.
            result.append("\\")
            index += 1
            if index < length:
                result.append(data[index])
                index += 1
            continue

        if char == '"':
            # Look ahead to determine whether this quote terminates the value.
            lookahead = index + 1
            while lookahead < length and data[lookahead] in " \t\r\n":
                lookahead += 1

            if lookahead >= length or data[lookahead] in ",}]":
                result.append('"')
                result.append(data[index + 1 :])
                return "".join(result)

            # Interior quote belonging to the HTML snippet -> escape it.
            result.append("\\\"")
            index += 1
            continue

        if char == "\n":
            result.append("\\n")
            index += 1
            continue

        if char == "\r":
            result.append("\\r")
            index += 1
            continue

        result.append(char)
        index += 1

    return data


def relaxed_json_loads(data: str, /) -> Any:
    """Lenient JSON loader that tolerates raw HTML snippets.

    The loader first attempts to parse the payload using ``json.loads``. When
    decoding fails we try to sanitise the ``html_snippet`` field by escaping
    problematic quotes and normalising raw newlines before retrying.
    """

    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        patched = _escape_html_snippet_field(data)
        if patched == data:
            raise
        return json.loads(patched)  # May still raise JSONDecodeError.


__all__ = ["relaxed_json_loads"]
