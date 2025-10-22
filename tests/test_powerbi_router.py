"""Integration tests for the Power BI device login endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.db import models


def _create_user(
    db_session: Session,
    *,
    email: str,
    password: str,
    tenant_id: str | None,
    public_client_id: str | None = None,
    cache_path: str | None = None,
) -> models.User:
    user = models.User(
        name="Mario",
        surname="Rossi",
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=False,
        aad_tenant_id=tenant_id,
        aad_public_client_id=public_client_id,
        aad_token_cache_path=cache_path,
    )
    user.set_scopes(["*"])
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _obtain_token(
    api_client: TestClient,
    *,
    email: str,
    password: str,
) -> str:
    response = api_client.post(
        "/auth/token",
        data={
            "grant_type": "password",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_device_login_uses_user_specific_configuration(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    password = "Password123!"
    user = _create_user(
        db_session,
        email="user@example.com",
        password=password,
        tenant_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        public_client_id="11111111-2222-3333-4444-555555555555",
        cache_path="/tmp/msal/cache.json",
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    captured: dict[str, object] = {}

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple store
            captured.update(kwargs)

        def acquire_token(self) -> dict[str, str]:
            return {"access_token": "dummy-token", "token_type": "Bearer"}

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "dummy-token"

    assert captured["client_id"] == user.aad_public_client_id
    assert (
        captured["authority"]
        == "https://login.microsoftonline.com/12345678-aaaa-bbbb-cccc-1234567890ab"
    )
    assert captured["token_cache_path"] == user.aad_token_cache_path

    settings = get_settings()
    assert captured["scopes"] == settings.msal_scopes
    assert captured["open_browser"] == settings.msal_open_browser


def test_device_login_requires_tenant_configuration(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "Password123!"
    user = _create_user(
        db_session,
        email="tenantless@example.com",
        password=password,
        tenant_id=None,
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant ID is not configured for this user"


def test_device_login_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post("/powerbi/device-login")

    assert response.status_code == 401
