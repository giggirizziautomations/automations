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
        self.created_pages: list[DummyPage] = []

    def on(self, event: str, handler: Callable[[], None]) -> None:  # pragma: no cover - exercised indirectly
        self._handlers.setdefault(event, []).append(handler)

    async def new_page(self) -> "DummyPage":
        page = DummyPage()
        self.created_pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True

    def emit(self, event: str) -> None:
        for handler in list(self._handlers.get(event, [])):
            handler()


class DummyPage:
    """Lightweight stub mimicking a Playwright page."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[], None]]] = {}
        self.url = ""
        self.goto_calls: list[tuple[str, str]] = []

    def on(self, event: str, handler: Callable[[], None]) -> None:  # pragma: no cover - exercised indirectly
        self._handlers.setdefault(event, []).append(handler)

    async def goto(self, url: str, wait_until: str) -> None:
        self.url = url
        self.goto_calls.append((url, wait_until))

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
    session_key = browser_module._session_key(user_id)
    browser_module._SESSIONS[session_key] = session

    shutdown_calls: list[tuple[object, object]] = []

    async def fake_shutdown(playwright, browser):
        shutdown_calls.append((playwright, browser))

    monkeypatch.setattr(browser_module, "_shutdown_browser", fake_shutdown)

    browser_module._register_session_cleanup(session_key, session)

    session.browser.emit("disconnected")
    await asyncio.sleep(0)

    assert session_key not in browser_module._SESSIONS
    assert shutdown_calls == [(session.playwright, session.browser)]
    browser_module._SESSIONS.clear()


async def test_cleanup_only_runs_once(monkeypatch) -> None:
    user_id = "user-1"
    session = browser_module.BrowserSession(
        playwright=DummyPlaywright(),
        browser=DummyBrowser(),
        page=DummyPage(),
    )
    session_key = browser_module._session_key(user_id)
    browser_module._SESSIONS[session_key] = session

    call_count = 0

    async def fake_shutdown(playwright, browser):
        nonlocal call_count
        call_count += 1

    monkeypatch.setattr(browser_module, "_shutdown_browser", fake_shutdown)

    browser_module._register_session_cleanup(session_key, session)

    session.page.emit("close")
    session.browser.emit("disconnected")
    await asyncio.sleep(0)

    assert call_count == 1
    assert session_key not in browser_module._SESSIONS
    browser_module._SESSIONS.clear()


async def test_open_webpage_creates_isolated_sessions(monkeypatch) -> None:
    async def fake_launch_browser(*, headless: bool = False):
        return DummyPlaywright(), DummyBrowser()

    monkeypatch.setattr(browser_module, "_launch_browser", fake_launch_browser)

    await browser_module.open_webpage("https://example.com/one", "user-1", session_id="s1")
    await browser_module.open_webpage("https://example.com/two", "user-1", session_id="s2")

    key_one = browser_module._session_key("user-1", "s1")
    key_two = browser_module._session_key("user-1", "s2")

    assert key_one in browser_module._SESSIONS
    assert key_two in browser_module._SESSIONS
    assert browser_module._SESSIONS[key_one] is not browser_module._SESSIONS[key_two]

    page_one = browser_module._SESSIONS[key_one].page
    page_two = browser_module._SESSIONS[key_two].page
    assert page_one.url == "https://example.com/one"
    assert page_two.url == "https://example.com/two"

    await browser_module.close_browser_session("user-1", session_id="s1")
    await browser_module.close_browser_session("user-1", session_id="s2")
    browser_module._SESSIONS.clear()


async def test_open_webpage_replaces_existing_session(monkeypatch) -> None:
    shutdown_calls: list[tuple[DummyPlaywright, DummyBrowser]] = []

    async def fake_shutdown(playwright, browser):
        shutdown_calls.append((playwright, browser))

    async def fake_launch_browser(*, headless: bool = False):
        return DummyPlaywright(), DummyBrowser()

    monkeypatch.setattr(browser_module, "_shutdown_browser", fake_shutdown)
    monkeypatch.setattr(browser_module, "_launch_browser", fake_launch_browser)

    await browser_module.open_webpage("https://example.com/start", "user-1", session_id="shared")
    first_session = browser_module._SESSIONS[browser_module._session_key("user-1", "shared")]

    await browser_module.open_webpage("https://example.com/next", "user-1", session_id="shared")
    second_session = browser_module._SESSIONS[browser_module._session_key("user-1", "shared")]

    assert first_session is not second_session
    assert shutdown_calls  # previous session was closed
    assert second_session.page.url == "https://example.com/next"

    await browser_module.close_browser_session("user-1", session_id="shared")
    browser_module._SESSIONS.clear()
