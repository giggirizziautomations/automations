"""Tests for the scraping instruction endpoints."""
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


def test_create_routine_requires_authentication(api_client: TestClient) -> None:
    response = api_client.post(
        "/scraping/routines",
        json={"url": "https://example.com", "mode": "headless"},
    )

    assert response.status_code == 401


def test_create_routine_uses_user_defaults(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/scraping/routines",
        json={"url": "https://example.com/login", "mode": "headless"},
        headers=headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == user.email
    assert payload["password"] == password
    assert payload["actions"] == []

    routine = db_session.query(models.ScrapingRoutine).one()
    assert routine.user_id == user.id
    assert routine.email == user.email
    assert security.decrypt_str(routine.password_encrypted) == password


def test_preview_generates_structured_action(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/scraping/actions/preview",
        json={
            "instruction": "Click the login button",
            "html_snippet": "<button id='login-btn'>Sign in</button>",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "click"
    assert data["selector"] == "#login-btn"
    assert data["metadata"]["text"] == "Sign in"
    assert data["metadata"]["confidence"] == 0.95
    assert data["metadata"]["raw_instruction"] == "Click the login button"


def test_preview_accepts_html_with_double_quotes(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/scraping/actions/preview",
        json={
            "instruction": "wait for the element to appear",
            "html_snippet": '<div data-bind="text: session.tileDisplayName">content</div>',
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "wait"
    assert data["selector"] in {
        "[data-bind=\"text: session.tileDisplayName\"]",
        "[data-bind='text: session.tileDisplayName']",
    }


def test_append_and_patch_actions(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    create_response = api_client.post(
        "/scraping/routines",
        json={"url": "https://example.com/login", "mode": "headless"},
        headers=headers,
    )
    routine_id = create_response.json()["id"]

    append_response = api_client.post(
        f"/scraping/routines/{routine_id}/actions",
        json={
            "instruction": "Click the login button",
            "html_snippet": "<button id='login-btn'>Login</button>",
        },
        headers=headers,
    )

    assert append_response.status_code == 200
    data = append_response.json()
    assert len(data["actions"]) == 1
    assert data["actions"][0]["selector"] == "#login-btn"

    patch_response = api_client.patch(
        f"/scraping/routines/{routine_id}/actions/0",
        json={
            "instruction": "Fill the email field with \"demo@example.com\"",
            "html_snippet": "<input id='email-field' name='email' />",
        },
        headers=headers,
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert len(patched["actions"]) == 1
    assert patched["actions"][0]["type"] == "fill"
    assert patched["actions"][0]["selector"] == "#email-field"
    assert patched["actions"][0]["input_text"] == "demo@example.com"
    assert patched["actions"][0]["metadata"]["label"] is None
    assert patched["actions"][0]["metadata"]["confidence"] == 0.95


def test_wait_action_extracts_duration(
    api_client: TestClient,
    db_session: Session,
) -> None:
    password = "secret123"
    user = _create_user(db_session=db_session, password=password)
    headers = _auth_headers(api_client, email=user.email, password=password)

    response = api_client.post(
        "/scraping/actions/preview",
        json={
            "instruction": "Wait for 2.5 seconds before continuing",
            "html_snippet": "<div data-testid='loader'></div>",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "wait"
    assert data["selector"] == "[data-testid='loader']"
    assert data["metadata"]["delay_seconds"] == 2.5
    assert data["metadata"]["confidence"] == 0.9


def test_routines_are_isolated_per_user(
    api_client: TestClient,
    db_session: Session,
) -> None:
    primary = _create_user(
        db_session=db_session,
        email="owner@example.com",
        password="primary-pass",
    )
    other = _create_user(
        db_session=db_session,
        email="other@example.com",
        password="other-pass",
        name="Jane",
    )

    owner_headers = _auth_headers(api_client, email=primary.email, password="primary-pass")
    other_headers = _auth_headers(api_client, email=other.email, password="other-pass")

    response = api_client.post(
        "/scraping/routines",
        json={"url": "https://example.com", "mode": "headless"},
        headers=owner_headers,
    )
    routine_id = response.json()["id"]

    forbidden_append = api_client.post(
        f"/scraping/routines/{routine_id}/actions",
        json={
            "instruction": "Click continue",
            "html_snippet": "<button id='continue'>Continue</button>",
        },
        headers=other_headers,
    )

    assert forbidden_append.status_code == 404
