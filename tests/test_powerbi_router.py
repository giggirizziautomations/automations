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
    scopes: list[str] | None = None,
    is_admin: bool = False,
) -> models.User:
    user = models.User(
        name="Mario",
        surname="Rossi",
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=is_admin,
        aad_tenant_id=tenant_id,
        aad_public_client_id=public_client_id,
        aad_token_cache_path=cache_path,
    )
    user.set_scopes(scopes or ["*"])
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
    flow_payload = {
        "user_code": "ABC123",
        "verification_uri": "https://login.microsoftonline.com/common/oauth2/deviceauth",
        "verification_uri_complete": "https://login.microsoftonline.com/common/oauth2/deviceauth?code=ABC123",
        "device_code": "device-code",
        "message": "Please authenticate",
        "expires_in": 900,
        "interval": 5,
    }

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple store
            captured.update(kwargs)

        def initiate_device_flow(self) -> dict[str, object]:
            return flow_payload

        def acquire_token_with_flow(self, flow: dict[str, object]) -> dict[str, str]:
            assert flow is flow_payload
        def acquire_token(self) -> dict[str, str]:
            return {"access_token": "dummy-token", "token_type": "Bearer"}

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    init_body = response.json()
    assert init_body["flow_id"]
    assert init_body["user_code"] == flow_payload["user_code"]
    assert init_body["verification_uri"] == flow_payload["verification_uri"]
    assert (
        init_body["verification_uri_complete"]
        == flow_payload["verification_uri_complete"]
    )
    assert init_body["message"] == flow_payload["message"]
    assert init_body["expires_in"] == flow_payload["expires_in"]
    assert init_body["interval"] == flow_payload["interval"]

    completion = api_client.post(
        "/powerbi/device-login/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"flow_id": init_body["flow_id"]},
    )

    assert completion.status_code == 200
    body = completion.json()
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
    response_init = api_client.post("/powerbi/device-login")

    assert response_init.status_code == 401

    response_complete = api_client.post(
        "/powerbi/device-login/complete", json={"flow_id": "dummy"}
    )

    assert response_complete.status_code == 401
    response = api_client.post("/powerbi/device-login")

    assert response.status_code == 401


def test_playwright_device_login_requires_scope(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "Password123!"
    user = _create_user(
        db_session,
        email="noscope@example.com",
        password=password,
        tenant_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        scopes=["reports:read"],
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    class _Automation:
        def __init__(self, *args: object, **kwargs: object) -> None:  # pragma: no cover - not executed
            raise AssertionError("Automation should not be instantiated without scope")

    monkeypatch.setattr(
        "app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation
    )

    response = api_client.post(
        "/powerbi/device-login/playwright",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "Missing required scopes" in response.json()["detail"]


def test_playwright_device_login_allows_bi_user(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "Password123!"
    user = _create_user(
        db_session,
        email="biuser@example.com",
        password=password,
        tenant_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        scopes=["bi-user"],
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    captured: dict[str, object] = {}
    captured_service_config: dict[str, object] = {}

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple stub
            captured_service_config.update(kwargs)
            self._open_browser = kwargs.get("open_browser")

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    class _Automation:
        def __init__(self, *, service: object, **_: object) -> None:
            captured["service"] = service

        def authenticate(self) -> dict[str, str]:
            return {"access_token": "dummy", "token_type": "Bearer"}

    monkeypatch.setattr(
        "app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation
    )

    response = api_client.post(
        "/powerbi/device-login/playwright",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "dummy"

    service = captured["service"]
    assert isinstance(service, _DummyService)
    assert captured_service_config["open_browser"] is False


def test_playwright_device_login_allows_admin(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "Password123!"
    user = _create_user(
        db_session,
        email="admin@example.com",
        password=password,
        tenant_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        scopes=["reports:read"],
        is_admin=True,
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    captured_service_config: dict[str, object] = {}

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple stub
            captured_service_config.update(kwargs)
            self._open_browser = kwargs.get("open_browser")

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    class _Automation:
        def __init__(self, *, service: object, **_: object) -> None:
            self._service = service

        def authenticate(self) -> dict[str, str]:
            return {"access_token": "admin-token", "token_type": "Bearer"}

    monkeypatch.setattr(
        "app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation
    )

    response = api_client.post(
        "/powerbi/device-login/playwright",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "admin-token"
    assert captured_service_config["open_browser"] is False
