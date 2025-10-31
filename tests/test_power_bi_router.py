"""Tests covering the Power BI export service endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.db import models


SCRAPING_ACTIONS = [
    {
        "type": "click",
        "selector": "#login-button",
        "description": "Click the login button",
        "target_tag": "button",
        "input_text": None,
        "metadata": {"confidence": 0.9},
    }
]

MERGED_DATASETS = [
    [
        {"vin": "1A4AABBC5KD501999", "region": "eu", "value": 100},
        {"vin": "1A4AABBC5KD501999", "region": "eu", "value": 150},
    ],
    [
        {"vin": "1A4AABBC5KD501999", "region": "eu", "value": 175},
        {"vin": "WAUZZZ", "region": "us", "value": 200},
    ],
]


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
    *,
    config_id: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "report_url": "https://example.com/report",
        "merge_strategy": "append",
        "scraping_actions": SCRAPING_ACTIONS,
    }
    if config_id is not None:
        payload["config_id"] = config_id
    response = client.put(
        "/power-bi/config",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _create_routine(
    *,
    db_session: Session,
    user: models.User,
    actions: list[dict[str, object]] | None = None,
) -> models.ScrapingRoutine:
    routine = models.ScrapingRoutine(
        user_id=user.id,
        url="https://example.com/login",
        mode="headed",
        email=user.email,
        password_encrypted=security.encrypt_str("routine-pass"),
        actions=list(actions or SCRAPING_ACTIONS),
    )
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


def test_bi_user_can_manage_configurations_and_run_service(
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

    config_response = _configure_power_bi(api_client, headers)
    config_id = config_response["id"]

    routine = _create_routine(db_session=db_session, user=user)
    patch_response = api_client.patch(
        "/power-bi/config/scraping-actions",
        json={"config_id": config_id, "routine_id": routine.id},
        headers=headers,
    )
    assert patch_response.status_code == 200
    patched_config = patch_response.json()
    assert patched_config["scraping_actions"] == SCRAPING_ACTIONS
    assert patched_config["export_format"] == "xlsx"

    list_response = api_client.get("/power-bi/config", headers=headers)
    assert list_response.status_code == 200
    configs = list_response.json()
    assert len(configs) == 1
    assert configs[0]["id"] == config_id

    detail_response = api_client.get(
        f"/power-bi/config/{config_id}", headers=headers
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["report_url"] == "https://example.com/report"

    run_response = api_client.post(
        f"/power-bi/run/{config_id}",
        json={
            "vin": "1A4AABBC5KD501999",
            "parameters": {"region": "eu"},
            "routine_id": routine.id,
            "dedup_parameter": "vin",
            "datasets": MERGED_DATASETS,
        },
        headers=headers,
    )
    assert run_response.status_code == 201
    body = run_response.json()
    assert body["vin"] == "1A4AABBC5KD501999".upper()
    assert body["status"] == "completed"
    assert body["export_format"] == "xlsx"
    assert body["payload"]["parameters"] == {"region": "eu"}
    assert body["payload"]["scraping_actions"] == SCRAPING_ACTIONS
    assert body["payload"]["routine_id"] == routine.id
    assert body["payload"]["merged_row_count"] == 2
    assert body["dedup_parameter"] == "vin"
    assert body["config_id"] == config_id
    assert body["routine_id"] == routine.id


def test_run_requires_configuration(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    user = _create_user(
        db_session=db_session,
        email="missing-config@example.com",
        password=password,
        scopes=["bi"],
    )
    routine = _create_routine(db_session=db_session, user=user)
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/power-bi/run/999",
        json={
            "vin": "123",
            "parameters": {},
            "routine_id": routine.id,
            "dedup_parameter": "vin",
            "datasets": [[{"vin": "123"}]],
        },
        headers=headers,
    )

    assert response.status_code == 404
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
    config = _configure_power_bi(api_client, bi_headers)
    routine = _create_routine(db_session=db_session, user=bi_user)
    api_client.patch(
        "/power-bi/config/scraping-actions",
        json={"config_id": config["id"], "routine_id": routine.id},
        headers=bi_headers,
    )
    api_client.post(
        f"/power-bi/run/{config['id']}",
        json={
            "vin": "WAUZZZ",
            "parameters": {"foo": "bar"},
            "routine_id": routine.id,
            "dedup_parameter": "vin",
            "datasets": MERGED_DATASETS,
        },
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
    assert all_records[0]["dedup_parameter"] == "vin"

    dataset_response = api_client.get(
        f"/power-bi/admin/exports/{routine.id}", headers=admin_headers
    )
    assert dataset_response.status_code == 200
    dataset = dataset_response.json()
    assert len(dataset) == 2
    values = {row["parameter_value"] for row in dataset}
    assert values == {"1A4AABBC5KD501999", "WAUZZZ"}

    search_response = api_client.get(
        "/power-bi/admin/exports/by-parameter/vin:WAUZZZ",
        headers=admin_headers,
    )
    assert search_response.status_code == 200
    filtered = search_response.json()
    assert len(filtered) == 1
    assert filtered[0]["parameter_value"] == "WAUZZZ"

    empty_search = api_client.get(
        "/power-bi/admin/exports/by-parameter/vin:UNKNOWN",
        headers=admin_headers,
    )
    assert empty_search.status_code == 200
    assert empty_search.json() == []
