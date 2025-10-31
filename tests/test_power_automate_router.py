from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.db import models
from app.services.power_automate import PowerAutomateInvocationResult


def _create_user(
    *,
    db_session: Session,
    email: str = "user@example.com",
    password: str = "plain-password",
    name: str = "John",
    surname: str = "Doe",
) -> models.User:
    user = models.User(
        name=name,
        surname=surname,
        email=email,
        password_encrypted=security.encrypt_str(password),
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


def test_create_and_list_flows(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    create_response = api_client.post(
        "/power-automate/flows",
        json={
            "name": "MFA Trigger",
            "url": "https://hooks.example.com/flow",
            "method": "POST",
            "body_template": {"code": "{{parameters.code}}"},
        },
        headers=headers,
    )

    assert create_response.status_code == 201
    flow_payload = create_response.json()
    assert flow_payload["name"] == "MFA Trigger"
    assert flow_payload["method"] == "POST"

    list_response = api_client.get("/power-automate/flows", headers=headers)
    assert list_response.status_code == 200
    flows = list_response.json()
    assert len(flows) == 1
    assert flows[0]["name"] == "MFA Trigger"
    assert flows[0]["url"] == "https://hooks.example.com/flow"


def test_load_flows_upserts_by_name(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    load_response = api_client.post(
        "/power-automate/flows/load",
        json={
            "flows": [
                {
                    "name": "MFA Trigger",
                    "url": "https://hooks.example.com/flow",
                    "method": "POST",
                    "body_template": {"code": "{{parameters.code}}"},
                },
                {
                    "name": "Notify",
                    "url": "https://hooks.example.com/notify",
                    "method": "POST",
                },
            ]
        },
        headers=headers,
    )

    assert load_response.status_code == 200
    loaded = load_response.json()
    assert [flow["name"] for flow in loaded] == ["MFA Trigger", "Notify"]

    update_response = api_client.post(
        "/power-automate/flows/load",
        json={
            "flows": [
                {
                    "name": "MFA Trigger",
                    "url": "https://hooks.example.com/flow2",
                    "method": "POST",
                    "timeout_seconds": 120,
                }
            ]
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert len(updated) == 1
    assert updated[0]["url"] == "https://hooks.example.com/flow2"
    assert updated[0]["timeout_seconds"] == 120

    list_response = api_client.get("/power-automate/flows", headers=headers)
    assert list_response.status_code == 200
    flows = sorted(list_response.json(), key=lambda item: item["name"])
    assert flows[0]["name"] == "MFA Trigger"
    assert flows[0]["url"] == "https://hooks.example.com/flow2"
    assert flows[1]["name"] == "Notify"

def test_invoke_flow_uses_service(api_client: TestClient, db_session: Session, monkeypatch) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    create_response = api_client.post(
        "/power-automate/flows",
        json={
            "name": "MFA Trigger",
            "url": "https://hooks.example.com/flow",
            "method": "POST",
        },
        headers=headers,
    )
    flow_id = create_response.json()["id"]

    captured: dict[str, Any] = {}

    async def fake_invoke_flow(**kwargs: Any) -> PowerAutomateInvocationResult:
        captured["kwargs"] = kwargs
        return PowerAutomateInvocationResult(
            flow_id=kwargs["flow_id"],
            status="success",
            http_status=202,
            response={"otp": "123456"},
            detail=None,
            failure_flow_triggered=False,
        )

    monkeypatch.setattr("app.services.power_automate.invoke_flow", fake_invoke_flow)

    response = api_client.post(
        f"/power-automate/flows/{flow_id}/invoke",
        json={"parameters": {"code": "987654"}},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["http_status"] == 202
    assert payload["response"] == {"otp": "123456"}

    assert captured["kwargs"]["user_id"] == user.id
    assert captured["kwargs"]["flow_id"] == flow_id
    assert captured["kwargs"]["payload"].parameters == {"code": "987654"}
    assert captured["kwargs"]["template_variables"]["user"]["email"] == user.email
