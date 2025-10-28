from __future__ import annotations

import json

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


def test_admin_can_update_scraping_actions(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="admin2@example.com",
        password=admin_password,
        is_admin=True,
    )

    target = models.ScrapingTarget(
        user_id=admin.id,
        site_name="update-site",
        url="https://example.com/login",
        recipe="default",
        parameters=json.dumps({"actions": [{"action": "wait", "milliseconds": 500}]}),
        notes="",
    )
    db_session.add(target)
    db_session.commit()

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    payload = {
        "actions": [
            {"action": "click", "selector": "#login"},
            {"action": "fill", "selector": "input[name=email]", "value": "demo"},
        ],
        "parameters": {"settle_ms": 250},
    }

    response = api_client.put(
        f"/scraping-targets/{target.id}/actions",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["parameters"]["settle_ms"] == 250
    assert data["parameters"]["actions"] == [
        {"action": "click", "selector": "#login"},
        {"action": "fill", "selector": "input[name=email]", "value": "demo"},
    ]

    db_session.refresh(target)
    stored = json.loads(target.parameters)
    assert stored["settle_ms"] == 250
    assert stored["actions"][0]["selector"] == "#login"


def test_update_scraping_actions_missing_target_returns_404(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="missing@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    payload = {
        "actions": [{"action": "wait", "milliseconds": 500}],
    }

    response = api_client.put(
        "/scraping-targets/999/actions",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Scraping target not found"


def test_preview_scraping_action_allows_form_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="form-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    response = api_client.post(
        "/scraping-targets/actions/preview",
        data={
            "html": '<div data-bind="text: session.tileDisplayName">demo</div>',
            "action": "click",
            "value": "ignored",
            "settle_ms": "0",
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"] == [
        {
            "action": "click",
            "selector": 'div[data-bind="text: session.tileDisplayName"]',
        },
    ]
    assert payload["settle_ms"] == 0


def test_preview_scraping_action_repairs_unescaped_quotes(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="json-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    raw_payload = (
        '{"html": "<div data-bind="text: session.tileDisplayName">demo</div>", '
        '"action": "click"}'
    )

    response = api_client.post(
        "/scraping-targets/actions/preview",
        data=raw_payload,
        headers={**headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0]["action"] == "click"
    assert payload["actions"][0]["selector"] == 'div[data-bind="text: session.tileDisplayName"]'


def test_preview_scraping_action_accepts_legacy_suggestion_field(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="legacy-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    response = api_client.post(
        "/scraping-targets/actions/preview",
        json={
            "html": "<div class=\"cta\">cta</div>",
            "suggestion": "click",
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0] == {"action": "click", "selector": "div.cta"}


def test_preview_scraping_action_accepts_nested_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="nested-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    response = api_client.post(
        "/scraping-targets/actions/preview",
        json={
            "payload": {
                "html": "<button class=\"cta\">cta</button>",
                "suggestion": "click",
            },
            "settle_ms": 250,
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0] == {"action": "click", "selector": "button.cta"}
    assert payload["settle_ms"] == 250


def test_preview_scraping_action_accepts_multipart_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="multipart-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    files = {
        "html": (None, '<button class="cta">cta</button>'),
        "action": (None, "click"),
        "settle_ms": (None, "1250"),
    }

    response = api_client.post(
        "/scraping-targets/actions/preview",
        files=files,
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0] == {"action": "click", "selector": "button.cta"}
    assert payload["settle_ms"] == 1250


def test_append_scraping_action_from_html_accepts_form_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="append-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    target = models.ScrapingTarget(
        user_id=admin.id,
        site_name="form-target",
        url="https://example.com/login",
        recipe="default",
        parameters=json.dumps({"actions": []}),
        notes="",
    )
    db_session.add(target)
    db_session.commit()

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    response = api_client.post(
        f"/scraping-targets/{target.id}/actions/from-html",
        data={
            "html": '<button id="submit-login" data-bind="click: login">Login</button>',
            "action": "click",
            "settle_ms": "750",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["actions"][-1]["selector"] == "#submit-login"
    assert body["parameters"]["settle_ms"] == 750


def test_append_scraping_action_from_html_accepts_nested_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="nested-append-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    target = models.ScrapingTarget(
        user_id=admin.id,
        site_name="nested-target",
        url="https://example.com/login",
        recipe="default",
        parameters=json.dumps({"actions": []}),
        notes="",
    )
    db_session.add(target)
    db_session.commit()

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    response = api_client.post(
        f"/scraping-targets/{target.id}/actions/from-html",
        json={
            "payload": {
                "html": '<button id="submit-login">Login</button>',
                "action": "click",
            },
            "settle_ms": 1500,
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["actions"][-1]["selector"] == "#submit-login"
    assert body["parameters"]["settle_ms"] == 1500


def test_append_scraping_action_from_html_accepts_multipart_payload(
    api_client: TestClient, db_session: Session
) -> None:
    admin_password = "Adm1nPass!"
    admin = _create_user(
        db_session=db_session,
        email="multipart-append-admin@example.com",
        password=admin_password,
        is_admin=True,
    )

    target = models.ScrapingTarget(
        user_id=admin.id,
        site_name="multipart-target",
        url="https://example.com/login",
        recipe="default",
        parameters=json.dumps({"actions": []}),
        notes="",
    )
    db_session.add(target)
    db_session.commit()

    headers = _auth_headers(api_client, email=admin.email, password=admin_password)

    files = {
        "html": (None, '<button id="submit-login">Login</button>'),
        "action": (None, "click"),
        "settle_ms": (None, "1750"),
    }

    response = api_client.post(
        f"/scraping-targets/{target.id}/actions/from-html",
        files=files,
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["actions"][-1]["selector"] == "#submit-login"
    assert body["parameters"]["settle_ms"] == 1750


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
