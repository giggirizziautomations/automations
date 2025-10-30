"""Unit tests for the browser helpers."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from app.core import browser as browser_module


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyPlaywright:
    """Lightweight stub mimicking the Playwright runtime."""

    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class DummyBrowser:
    """Lightweight stub mimicking a Playwright browser."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[], None]]] = {}
        self.closed = False

    def on(self, event: str, handler: Callable[[], None]) -> None:  # pragma: no cover - exercised indirectly
        self._handlers.setdefault(event, []).append(handler)

    async def close(self) -> None:
        self.closed = True

    def emit(self, event: str) -> None:
        for handler in list(self._handlers.get(event, [])):
            handler()


class DummyPage:
    """Lightweight stub mimicking a Playwright page."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[], None]]] = {}

    def on(self, event: str, handler: Callable[[], None]) -> None:  # pragma: no cover - exercised indirectly
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str) -> None:
        for handler in list(self._handlers.get(event, [])):
            handler()


async def test_cleanup_runs_when_browser_disconnects(monkeypatch) -> None:
    user_id = "user-1"
    session = browser_module.BrowserSession(
        playwright=DummyPlaywright(),
        browser=DummyBrowser(),
        page=DummyPage(),
    )
    browser_module._SESSIONS[user_id] = session

    shutdown_calls: list[tuple[object, object]] = []

    async def fake_shutdown(playwright, browser):
        shutdown_calls.append((playwright, browser))

    monkeypatch.setattr(browser_module, "_shutdown_browser", fake_shutdown)

    browser_module._register_session_cleanup(user_id, session)

    session.browser.emit("disconnected")
    await asyncio.sleep(0)

    assert user_id not in browser_module._SESSIONS
    assert shutdown_calls == [(session.playwright, session.browser)]
    browser_module._SESSIONS.clear()


async def test_cleanup_only_runs_once(monkeypatch) -> None:
    user_id = "user-1"
    session = browser_module.BrowserSession(
        playwright=DummyPlaywright(),
        browser=DummyBrowser(),
        page=DummyPage(),
    )
    browser_module._SESSIONS[user_id] = session

    call_count = 0

    async def fake_shutdown(playwright, browser):
        nonlocal call_count
        call_count += 1

    monkeypatch.setattr(browser_module, "_shutdown_browser", fake_shutdown)

    browser_module._register_session_cleanup(user_id, session)

    session.page.emit("close")
    session.browser.emit("disconnected")
    await asyncio.sleep(0)

    assert call_count == 1
    assert user_id not in browser_module._SESSIONS
    browser_module._SESSIONS.clear()
