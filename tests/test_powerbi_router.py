import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.db import models
from app.services import DeviceCodeLoginError


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
        scopes=["bi-user"],
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    captured_service_kwargs: dict[str, object] = {}
    captured_automation_service: object | None = None

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple store
            captured_service_kwargs.update(kwargs)

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    class _Automation:
        def __init__(self, *, service: object, **_: object) -> None:
            nonlocal captured_automation_service
            captured_automation_service = service

        def authenticate(self) -> dict[str, str]:
            return {"access_token": "dummy-token", "token_type": "Bearer"}

    monkeypatch.setattr("app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "dummy-token"

    assert captured_service_kwargs["client_id"] == user.aad_public_client_id
    assert (
        captured_service_kwargs["authority"]
        == "https://login.microsoftonline.com/12345678-aaaa-bbbb-cccc-1234567890ab"
    )
    assert captured_service_kwargs["token_cache_path"] == user.aad_token_cache_path

    settings = get_settings()
    assert captured_service_kwargs["scopes"] == settings.msal_scopes
    assert captured_service_kwargs["open_browser"] is False

    assert isinstance(captured_automation_service, _DummyService)


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
        scopes=["bi-user"],
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


def test_device_login_requires_scope(
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
        def __init__(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
            raise AssertionError("Automation should not be instantiated without scope")

    monkeypatch.setattr("app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "Missing required scopes" in response.json()["detail"]


def test_device_login_allows_admin(
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

    captured_service_kwargs: dict[str, object] = {}

    class _DummyService:
        def __init__(self, **kwargs: object) -> None:  # pragma: no cover - simple store
            captured_service_kwargs.update(kwargs)

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    class _Automation:
        def __init__(self, *, service: object, **_: object) -> None:
            self._service = service

        def authenticate(self) -> dict[str, str]:
            return {"access_token": "admin-token", "token_type": "Bearer"}

    monkeypatch.setattr("app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "admin-token"
    assert captured_service_kwargs["open_browser"] is False


def test_device_login_propagates_errors(
    api_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "Password123!"
    user = _create_user(
        db_session,
        email="error@example.com",
        password=password,
        tenant_id="12345678-aaaa-bbbb-cccc-1234567890ab",
        scopes=["bi-user"],
    )

    token = _obtain_token(api_client, email=user.email, password=password)

    class _DummyService:
        def __init__(self, **_: object) -> None:  # pragma: no cover - simple stub
            pass

    monkeypatch.setattr("app.routers.powerbi.DeviceCodeLoginService", _DummyService)

    class _Automation:
        def __init__(self, *, service: object, **_: object) -> None:
            self._service = service

        def authenticate(self) -> dict[str, str]:
            raise DeviceCodeLoginError("boom")

    monkeypatch.setattr("app.routers.powerbi.PlaywrightDeviceLoginAutomation", _Automation)

    response = api_client.post(
        "/powerbi/device-login",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error"] == "device_login_failed"
    assert detail["message"] == "boom"
