from __future__ import annotations

import pytest

from app.scraping.helpers import build_action_step, build_actions_document


def test_build_action_step_click_uses_id_selector() -> None:
    html = '<button id="submit-login" class="btn primary">Login</button>'
    action = build_action_step(html, "click")
    assert action == {"action": "click", "selector": "#submit-login"}


def test_build_action_step_fill_infers_placeholder_value() -> None:
    html = '<input type="email" name="email" placeholder="user@example.com" />'
    action = build_action_step(html, "input text")
    assert action["action"] == "fill"
    assert action["selector"] == 'input[name="email"]'
    assert action["value"] == "user@example.com"


def test_build_action_step_wait_without_element_defaults_to_timeout() -> None:
    action = build_action_step("<!-- comment only -->", "wait")
    assert action == {"action": "wait", "milliseconds": 1000}


def test_build_actions_document_wraps_action() -> None:
    html = '<div class="alert banner">Ready</div>'
    document = build_actions_document(html, "wait", settle_ms=750)
    assert document["settle_ms"] == 750
    assert document["actions"][0]["selector"] == "div.alert.banner"


def test_build_action_step_unknown_suggestion_raises() -> None:
    html = '<span class="label">Status</span>'
    with pytest.raises(ValueError):
        build_action_step(html, "scroll")
