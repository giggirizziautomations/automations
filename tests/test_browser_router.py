"""Tests for the browser automation endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.db import models


def _create_user(
    *,
    db_session: Session,
    email: str = "user@example.com",
    password: str = "plain-password",
    name: str = "John",
    surname: str = "Doe",
    is_admin: bool = False,
) -> models.User:
    user = models.User(
        name=name,
        surname=surname,
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=is_admin,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _auth_headers(client: TestClient, *, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/token",
        data={
            "grant_type": "password",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_open_browser_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/browser/open",
        json={"url": "https://example.com"},
    )

    assert response.status_code == 401


def test_open_browser_uses_authenticated_user(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    captured: dict[str, tuple[str, str, str | None]] = {}

    async def fake_open_webpage(
        url: str,
        invoked_by: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, str]:
        captured["args"] = (url, invoked_by, session_id)
        return {
            "status": "opened",
            "url": url,
            "user": invoked_by,
            "session_id": session_id or "default",
        }

    monkeypatch.setattr("app.routers.browser.open_webpage", fake_open_webpage)

    response = api_client.post(
        "/browser/open",
        json={"url": "https://example.com"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["user"] == str(user.id)
    assert captured["args"][1] == str(user.id)
    assert captured["args"][2] is None
    assert response.json()["session_id"] == "default"


def test_open_browser_honours_requested_session(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    captured: dict[str, tuple[str, str, str | None]] = {}

    async def fake_open_webpage(
        url: str,
        invoked_by: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, str]:
        captured["args"] = (url, invoked_by, session_id)
        return {
            "status": "opened",
            "url": url,
            "user": invoked_by,
            "session_id": session_id or "default",
        }

    monkeypatch.setattr("app.routers.browser.open_webpage", fake_open_webpage)

    response = api_client.post(
        "/browser/open",
        json={"url": "https://example.com", "session_id": "session-1"},
        headers=headers,
    )

    assert response.status_code == 200
    assert captured["args"] == ("https://example.com/", str(user.id), "session-1")
    assert response.json()["session_id"] == "session-1"
