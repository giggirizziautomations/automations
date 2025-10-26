from __future__ import annotations

import asyncio

from app.core import security
from app.core.scraping import _inject_default_credentials
from app.db import models
from app.scraping import recipes


class DummyPage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    async def fill(self, selector: str, value: str, timeout: int | None = None) -> None:
        self.calls.append((selector, value, timeout))


def test_execute_actions_injects_email_when_missing() -> None:
    page = DummyPage()
    result: recipes.ScrapingResult = {}

    asyncio.run(
        recipes.execute_actions(
            page,
            actions=[{"action": "fill", "selector": "input[name=email]"}],
            result=result,
            context={"email": "runner@example.com"},
        )
    )

    assert page.calls == [("input[name=email]", "runner@example.com", None)]


def test_execute_actions_injects_password_when_missing() -> None:
    page = DummyPage()
    result: recipes.ScrapingResult = {}

    asyncio.run(
        recipes.execute_actions(
            page,
            actions=[{"action": "fill", "selector": "#password"}],
            result=result,
            context={"password": "secret"},
        )
    )

    assert page.calls == [("#password", "secret", None)]


def test_execute_actions_preserves_explicit_values() -> None:
    page = DummyPage()
    result: recipes.ScrapingResult = {}

    asyncio.run(
        recipes.execute_actions(
            page,
            actions=[{"action": "fill", "selector": "#custom", "value": "explicit"}],
            result=result,
            context={"email": "runner@example.com"},
        )
    )

    assert page.calls == [("#custom", "explicit", None)]


def test_inject_default_credentials_prefers_runner_user(test_environment) -> None:
    owner = models.User(
        id=1,
        name="Owner",
        surname="User",
        email="owner@example.com",
        password_encrypted=security.encrypt_str("owner-pass"),
        scopes="",
    )

    target = models.ScrapingTarget(
        user_id=owner.id,
        site_name="demo",
        url="https://example.com",
        recipe="default",
        parameters="{}",
        notes="",
    )
    target.user = owner

    runner = models.User(
        id=2,
        name="Runner",
        surname="User",
        email="runner@example.com",
        password_encrypted=security.encrypt_str("runner-pass"),
        scopes="",
    )

    enriched = _inject_default_credentials({}, target=target, runner=runner)

    assert enriched["email"] == runner.email
    assert enriched["password"] == "runner-pass"


def test_inject_default_credentials_respects_existing_values(test_environment) -> None:
    owner = models.User(
        id=10,
        name="Owner",
        surname="User",
        email="owner@example.com",
        password_encrypted=security.encrypt_str("owner-pass"),
        scopes="",
    )

    target = models.ScrapingTarget(
        user_id=owner.id,
        site_name="demo",
        url="https://example.com",
        recipe="default",
        parameters="{}",
        notes="",
    )
    target.user = owner

    payload = {
        "email": "custom@example.com",
        "password": "custom-pass",
    }

    enriched = _inject_default_credentials(payload, target=target, runner=None)

    assert enriched["email"] == "custom@example.com"
    assert enriched["password"] == "custom-pass"
