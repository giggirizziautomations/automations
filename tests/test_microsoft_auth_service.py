from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core import security
from app.core.auth import Principal
from app.db import models
from app.services.microsoft_auth import (
    MicrosoftAuthenticationError,
    MicrosoftAuthenticationService,
)


class _Clock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime.utcnow()

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class _DummyElement:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class _DummyPage:
    def __init__(self, element: _DummyElement) -> None:
        self._element = element
        self.wait_calls: list[tuple[str, float | None]] = []

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> _DummyElement:
        self.wait_calls.append((selector, timeout))
        return self._element


class _DummySession:
    def __init__(self, page: _DummyPage) -> None:
        self.page = page
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _create_user(db_session: Session, *, email: str, password: str) -> models.User:
    user = models.User(
        name="Test",
        surname="User",
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=False,
    )
    user.set_scopes(["*"])
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_principal(user: models.User) -> Principal:
    return Principal(sub=str(user.id), scopes=user.get_scopes(), is_admin=user.is_admin, user_id=user.id)


def test_returns_recent_token_without_automation(db_session: Session) -> None:
    user = _create_user(db_session, email="user@example.com", password="Secret123!")
    token = models.MicrosoftServiceToken(
        user_id=user.id,
        access_token="cached-token",
        created_at=datetime.utcnow(),
    )
    db_session.add(token)
    db_session.commit()

    launcher_called = False

    def _launcher(_: str) -> _DummySession:  # pragma: no cover - defensive
        nonlocal launcher_called
        launcher_called = True
        raise AssertionError("Browser should not be launched when token is fresh")

    service = MicrosoftAuthenticationService(db=db_session, browser_launcher=_launcher)

    result = service.authenticate(website="https://contoso.com", principal=_create_principal(user))

    assert result.access_token == "cached-token"
    assert launcher_called is False


def test_triggers_flow_and_returns_new_token(db_session: Session) -> None:
    password = "Secret123!"
    user = _create_user(db_session, email="user@example.com", password=password)

    clock = _Clock()
    element = _DummyElement("123456")
    page = _DummyPage(element)
    session = _DummySession(page)

    def _launcher(url: str) -> _DummySession:
        assert url == "https://contoso.com"
        return session

    created_tokens: list[models.MicrosoftServiceToken] = []

    def _flow_invoker(number: str, email: str, plain_password: str) -> None:
        assert number == "123456"
        assert email == user.email
        assert plain_password == password
        token = models.MicrosoftServiceToken(
            user_id=user.id,
            access_token="new-token",
            created_at=clock(),
        )
        db_session.add(token)
        db_session.commit()
        created_tokens.append(token)

    service = MicrosoftAuthenticationService(
        db=db_session,
        browser_launcher=_launcher,
        flow_invoker=_flow_invoker,
        poll_interval=0.0,
        wait_timeout=1.0,
        clock=clock,
        sleeper=lambda _: None,
    )

    result = service.authenticate(website="https://contoso.com", principal=_create_principal(user))

    assert result.access_token == "new-token"
    assert created_tokens[0].id == result.id
    assert session.closed is True
    assert page.wait_calls == [
        ("[data-automation-id='authenticator-number']", 30_000)
    ]


def test_raises_when_token_not_created(db_session: Session) -> None:
    password = "Secret123!"
    user = _create_user(db_session, email="user@example.com", password=password)

    clock = _Clock()
    element = _DummyElement("654321")
    page = _DummyPage(element)
    session = _DummySession(page)

    def _launcher(_: str) -> _DummySession:
        return session

    def _flow_invoker(_: str, __: str, ___: str) -> None:
        pass

    def _sleeper(seconds: float) -> None:
        clock.advance(seconds)

    service = MicrosoftAuthenticationService(
        db=db_session,
        browser_launcher=_launcher,
        flow_invoker=_flow_invoker,
        poll_interval=0.1,
        wait_timeout=0.3,
        clock=clock,
        sleeper=_sleeper,
    )

    with pytest.raises(MicrosoftAuthenticationError):
        service.authenticate(website="https://contoso.com", principal=_create_principal(user))

    assert session.closed is True


def test_requires_user_context(db_session: Session) -> None:
    password = "Secret123!"
    user = _create_user(db_session, email="user@example.com", password=password)
    principal = Principal(sub="client", scopes=user.get_scopes(), is_admin=False, client_id="client")

    service = MicrosoftAuthenticationService(db=db_session, browser_launcher=lambda _: None)

    with pytest.raises(MicrosoftAuthenticationError):
        service.authenticate(website="https://contoso.com", principal=principal)
