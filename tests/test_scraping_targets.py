from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.scraping import load_target
from app.db import models


def _create_user(
    *,
    db_session: Session,
    email: str,
    password: str,
    is_admin: bool = False,
) -> models.User:
    user = models.User(
        name="Test",
        surname="User",
        email=email,
        password_encrypted=security.encrypt_str(password),
        is_admin=is_admin,
    )
    if is_admin:
        user.set_scopes(["*"])
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


def test_admin_can_create_scraping_target(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    payload = {
        "user_id": admin.id,
        "site_name": "example-site",
        "url": "https://example.com/login",
        "parameters": {"settle_ms": 500},
        "notes": "Example",
        "password": "site-secret",
    }

    response = api_client.post("/scraping-targets", json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["site_name"] == payload["site_name"]
    assert body["has_password"] is True
    assert body["parameters"] == {"settle_ms": 500}

    target = (
        db_session.query(models.ScrapingTarget)
        .filter(models.ScrapingTarget.site_name == payload["site_name"])
        .first()
    )
    assert target is not None
    assert target.password_encrypted is not None
    assert target.password_encrypted != payload["password"]
    assert security.decrypt_str(target.password_encrypted) == payload["password"]


def test_scraping_target_resolves_user_password(db_session: Session) -> None:
    password = "plain-pass"
    user = _create_user(
        db_session=db_session,
        email="user@example.com",
        password=password,
        is_admin=False,
    )
    target = models.ScrapingTarget(
        user_id=user.id,
        site_name="no-password",
        url="https://example.com",
        parameters="{}",
        notes="",
    )
    db_session.add(target)
    db_session.commit()

    loaded = load_target(db_session, user_id=user.id, site_name="no-password")
    assert loaded.resolve_password() == password


def test_scraping_target_resolves_specific_password(db_session: Session) -> None:
    user = _create_user(
        db_session=db_session,
        email="owner@example.com",
        password="owner-pass",
        is_admin=False,
    )
    target_password = "target-pass"
    target = models.ScrapingTarget(
        user_id=user.id,
        site_name="custom-password",
        url="https://example.com",
        parameters="{}",
        notes="",
    )
    target.set_password(target_password)
    db_session.add(target)
    db_session.commit()

    loaded = load_target(db_session, user_id=user.id, site_name="custom-password")
    assert loaded.resolve_password() == target_password
