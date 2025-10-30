"""Tests for the scraping instruction endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.core.browser import BrowserSessionNotFound
from app.core.scraping import generate_scraping_action
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


class _FakePage:
    def __init__(self, start_url: str) -> None:
        self.current_url = start_url
        self.calls: list[tuple[str, ...]] = []

    @property
    def url(self) -> str:
        return self.current_url

    async def goto(self, url: str, *, wait_until: str = "networkidle") -> None:
        self.current_url = url
        self.calls.append(("goto", url, wait_until))

    async def click(self, selector: str) -> None:
        self.calls.append(("click", selector))

    async def fill(self, selector: str, value: str) -> None:
        self.calls.append(("fill", selector, value))

    async def select_option(self, selector: str, value: str) -> None:
        self.calls.append(("select", selector, value))

    async def wait_for_timeout(self, timeout: float) -> None:
        self.calls.append(("wait", timeout))

    async def evaluate(self, expression: str) -> None:
        self.calls.append(("evaluate", expression))


def test_execute_routine_runs_actions_with_credentials(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    user_password = "user-pass"
    routine_password = "routine-secret"
    user = _create_user(db_session=db_session, password=user_password)
    routine = models.ScrapingRoutine(
        user_id=user.id,
        url="https://example.com/login",
        mode="headed",
        email=user.email,
        password_encrypted=security.encrypt_str(routine_password),
        actions=[
            generate_scraping_action(
                "Fill the email field",
                "<input id='email-field' name='email' type='email' />",
            ),
            generate_scraping_action(
                "Enter the account password",
                "<input id='password-field' type='password' />",
            ),
            generate_scraping_action(
                "Click the submit button",
                "<button id='submit-btn'>Sign in</button>",
            ),
        ],
    )
    db_session.add(routine)
    db_session.commit()

    page = _FakePage(start_url=routine.url)
    captured_user: dict[str, str] = {}

    def fake_get_active_page(user_id: str) -> _FakePage:
        captured_user["id"] = user_id
        return page

    monkeypatch.setattr("app.routers.scraping.get_active_page", fake_get_active_page)

    headers = _auth_headers(api_client, email=user.email, password=user_password)
    response = api_client.post(
        f"/scraping/routines/{routine.id}/execute",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["routine_id"] == routine.id
    assert payload["url"] == routine.url
    assert captured_user["id"] == str(user.id)

    results = payload["results"]
    assert [result["type"] for result in results] == ["fill", "fill", "click"]
    assert results[0]["input_text"] == user.email
    assert results[1]["input_text"] == routine_password
    assert results[2]["status"] == "success"

    assert ("fill", "#email-field", user.email) in page.calls
    assert ("fill", "#password-field", routine_password) in page.calls
    assert ("click", "#submit-btn") in page.calls


def test_execute_routine_opens_browser_if_missing(
    api_client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    user_password = "user-pass"
    user = _create_user(db_session=db_session, password=user_password)
    routine = models.ScrapingRoutine(
        user_id=user.id,
        url="https://example.com/login",
        mode="headed",
        email=user.email,
        password_encrypted=security.encrypt_str("routine-secret"),
    )
    db_session.add(routine)
    db_session.commit()

    page = _FakePage(start_url=routine.url)
    open_calls: list[tuple[str, str]] = []
    ready = {"opened": False}

    def fake_get_active_page(user_id: str) -> _FakePage:
        if not ready["opened"]:
            raise BrowserSessionNotFound(user_id)
        return page

    async def fake_open_webpage(url: str, invoked_by: str) -> dict[str, str]:
        ready["opened"] = True
        open_calls.append((url, invoked_by))
        return {"status": "opened", "url": url, "user": invoked_by}

    monkeypatch.setattr("app.routers.scraping.get_active_page", fake_get_active_page)
    monkeypatch.setattr("app.routers.scraping.open_webpage", fake_open_webpage)

    headers = _auth_headers(api_client, email=user.email, password=user_password)
    response = api_client.post(
        f"/scraping/routines/{routine.id}/execute",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert open_calls == [(routine.url, str(user.id))]
