"""Password grant authentication tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import security
from app.db import models
from sqlalchemy.orm import Session


def test_password_login_success(api_client: TestClient, db_session: Session) -> None:
    password = "plain-password"
    user = models.User(
        name="Mario",
        surname="Rossi",
        email="mario.rossi@example.com",
        password_encrypted=security.encrypt_str(password),
        is_admin=False,
    )
    user.set_scopes(["users:read"])
    db_session.add(user)
    db_session.commit()

    response = api_client.post(
        "/auth/token",
        data={
            "grant_type": "password",
            "email": "mario.rossi@example.com",
            "password": password,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    assert body["scope"] == "users:read"
