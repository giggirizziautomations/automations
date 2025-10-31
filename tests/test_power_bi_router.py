"""Tests covering the Power BI export service endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.db import models


def _create_user(
    *,
    db_session: Session,
    email: str,
    password: str,
    is_admin: bool = False,
    scopes: list[str] | None = None,
) -> models.User:
    user = models.User(
        name="Test",
        surname="User",
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=is_admin,
    )
    if scopes:
        user.set_scopes(scopes)
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


def _configure_power_bi(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.put(
        "/power-bi/config",
        json={
            "report_url": "https://example.com/report",
            "export_format": "csv",
            "merge_strategy": "append",
        },
        headers=headers,
    )
    assert response.status_code == 200


def test_bi_user_can_configure_and_run_service(
    api_client: TestClient, db_session: Session
) -> None:
    password = "secret123"
    user = _create_user(
        db_session=db_session,
        email="bi-user@example.com",
        password=password,
        scopes=["bi"],
    )

    headers = _auth_headers(api_client, email=user.email, password=password)

    _configure_power_bi(api_client, headers)

    response = api_client.get("/power-bi/config", headers=headers)
    assert response.status_code == 200
    config = response.json()
    assert config["report_url"] == "https://example.com/report"
    assert config["export_format"] == "csv"
    assert config["merge_strategy"] == "append"

    run_response = api_client.post(
        "/power-bi/run",
        json={"vin": "1A4AABBC5KD501999", "parameters": {"region": "eu"}},
        headers=headers,
    )
    assert run_response.status_code == 201
    body = run_response.json()
    assert body["vin"] == "1A4AABBC5KD501999".upper()
    assert body["status"] == "completed"
    assert body["payload"]["parameters"] == {"region": "eu"}


def test_run_requires_configuration(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    user = _create_user(
        db_session=db_session,
        email="missing-config@example.com",
        password=password,
        scopes=["bi"],
    )
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/power-bi/run",
        json={"vin": "123", "parameters": {}},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Power BI service configuration is missing"


def test_admin_endpoints_require_admin(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    bi_user = _create_user(
        db_session=db_session,
        email="bi-lister@example.com",
        password=password,
        scopes=["bi"],
    )
    bi_headers = _auth_headers(api_client, email=bi_user.email, password=password)
    _configure_power_bi(api_client, bi_headers)
    api_client.post(
        "/power-bi/run",
        json={"vin": "WAUZZZ", "parameters": {"foo": "bar"}},
        headers=bi_headers,
    )

    response = api_client.get("/power-bi/admin/exports", headers=bi_headers)
    assert response.status_code == 403

    admin = _create_user(
        db_session=db_session,
        email="admin@example.com",
        password=password,
        is_admin=True,
    )
    admin_headers = _auth_headers(api_client, email=admin.email, password=password)

    list_response = api_client.get("/power-bi/admin/exports", headers=admin_headers)
    assert list_response.status_code == 200
    all_records = list_response.json()
    assert len(all_records) == 1
    assert all_records[0]["vin"] == "WAUZZZ"

    search_response = api_client.get(
        "/power-bi/admin/exports/by-vin/WAUZZZ",
        headers=admin_headers,
    )
    assert search_response.status_code == 200
    filtered = search_response.json()
    assert len(filtered) == 1
    assert filtered[0]["vin"] == "WAUZZZ"

    empty_search = api_client.get(
        "/power-bi/admin/exports/by-vin/UNKNOWN",
        headers=admin_headers,
    )
    assert empty_search.status_code == 200
    assert empty_search.json() == []
