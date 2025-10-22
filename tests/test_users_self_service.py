"""Tests for self-service user profile management."""
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


def test_user_can_update_own_profile(
    api_client: TestClient, db_session: Session
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)

    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.patch(
        "/users",
        json={"name": "Johnny", "surname": "Updated"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Johnny"
    assert body["surname"] == "Updated"
    assert body["email"] == user.email

    db_session.refresh(user)
    assert user.name == "Johnny"
    assert user.surname == "Updated"


def test_user_cannot_modify_admin_fields(
    api_client: TestClient, db_session: Session
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)

    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.patch(
        "/users",
        json={"is_admin": True},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not allowed to modify administrative fields"

    db_session.refresh(user)
    assert user.is_admin is False


def test_non_admin_cannot_list_users(api_client: TestClient, db_session: Session) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)

    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.get("/users", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator privileges required"

