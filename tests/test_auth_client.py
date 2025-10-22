"""Client credentials authentication tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import security
from app.db import models
from sqlalchemy.orm import Session


def test_client_credentials_login(api_client: TestClient, db_session: Session) -> None:
    client_secret = "top-secret"
    client = models.ClientApp(
        name="Reporting Service",
        client_id="client-123",
        client_secret_encrypted=security.encrypt_str(client_secret),
    )
    client.set_scopes(["reports:read"])
    db_session.add(client)
    db_session.commit()

    response = api_client.get(
        "/auth/token",
        params={
            "client_id": "client-123",
            "client_secret": client_secret,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    assert body["scope"] == "reports:read"
