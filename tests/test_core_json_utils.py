"""Tests for :mod:`app.core.json_utils`."""
from __future__ import annotations

import textwrap

import pytest

from app.core.json_utils import relaxed_json_loads


@pytest.mark.parametrize(
    "payload, expected",
    [
        (
            """{"instruction": "click", "html_snippet": "<button>Go</button>"}""",
            {
                "instruction": "click",
                "html_snippet": "<button>Go</button>",
            },
        ),
        (
            textwrap.dedent(
                '''
                {
                  "instruction": "fill the field with password",
                  "html_snippet": "<input name="passwd" type="password"
                    placeholder="Password">",
                  "metadata": {"note": "raw snippet"}
                }
                '''
            ),
            {
                "instruction": "fill the field with password",
                "html_snippet": '<input name="passwd" type="password"\n    placeholder="Password">',
                "metadata": {"note": "raw snippet"},
            },
        ),
    ],
)
def test_relaxed_json_loads_handles_html_snippet(payload: str, expected: dict[str, object]) -> None:
    """Ensure ``relaxed_json_loads`` fixes malformed HTML snippet payloads."""

    data = relaxed_json_loads(payload)
    assert data == expected
