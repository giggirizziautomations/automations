"""Tests for the MSAL device code login service."""
from __future__ import annotations

import pytest

from app.services import DeviceCodeLoginError, DeviceCodeLoginService


class _FakeClient:
    """Simple MSAL client stand-in used by the tests."""

    def __init__(
        self,
        flow_response: dict,
        token_response: dict,
        *,
        accounts: list[dict] | None = None,
        silent_response: dict | None = None,
    ) -> None:
        self._flow_response = flow_response
        self._token_response = token_response
        self.initiated_with: list[list[str]] = []
        self.received_flow: list[dict] = []
        self._accounts = accounts or []
        self._silent_response = silent_response

    def initiate_device_flow(self, scopes: list[str]) -> dict:
        self.initiated_with.append(scopes)
        return self._flow_response

    def acquire_token_by_device_flow(self, flow: dict) -> dict:
        self.received_flow.append(flow)
        return self._token_response

    def get_accounts(self) -> list[dict]:
        return self._accounts

    def acquire_token_silent(
        self, scopes: list[str], *, account: dict
    ) -> dict | None:
        if self._silent_response and account in self._accounts:
            return self._silent_response
        return None


def test_device_code_service_opens_browser_when_flow_succeeds() -> None:
    """The browser opener is invoked with the verification URL when provided."""

    flow = {
        "user_code": "ABCD1234",
        "verification_uri_complete": "https://login.microsoftonline.com/complete",
    }
    token = {"access_token": "token", "token_type": "Bearer"}
    client = _FakeClient(flow, token)
    opened_urls: list[str] = []

    service = DeviceCodeLoginService(
        client_id="client-id",
        authority="https://login.microsoftonline.com/common",
        scopes=["scope/.default"],
        client=client,
        browser_opener=opened_urls.append,
    )

    result = service.acquire_token()

    assert result == token
    assert opened_urls == ["https://login.microsoftonline.com/complete"]
    assert client.initiated_with == [["scope/.default"]]
    assert client.received_flow == [flow]


def test_device_code_service_raises_error_when_token_missing() -> None:
    """A missing access token results in a DeviceCodeLoginError."""

    flow = {
        "user_code": "ABCD1234",
        "verification_uri": "https://login.microsoftonline.com/common/oauth2/deviceauth",
    }
    token = {"error": "authorization_pending", "error_description": "pending"}
    client = _FakeClient(flow, token)

    service = DeviceCodeLoginService(
        client_id="client-id",
        authority="https://login.microsoftonline.com/common",
        scopes=["scope/.default"],
        client=client,
        open_browser=False,
    )

    with pytest.raises(DeviceCodeLoginError):
        service.acquire_token()


def test_device_code_service_builds_fallback_verification_url() -> None:
    """If verification_uri_complete is missing, fall back to composing the URL."""

    flow = {
        "user_code": "ABCD1234",
        "verification_uri": "https://login.microsoftonline.com/common/oauth2/deviceauth",
    }
    token = {"access_token": "token", "token_type": "Bearer"}
    client = _FakeClient(flow, token)
    opened_urls: list[str] = []

    service = DeviceCodeLoginService(
        client_id="client-id",
        authority="https://login.microsoftonline.com/common",
        scopes=["scope/.default"],
        client=client,
        browser_opener=opened_urls.append,
    )

    service.acquire_token()

    assert opened_urls == [
        "https://login.microsoftonline.com/common/oauth2/deviceauth?code=ABCD1234"
    ]


def test_device_code_service_uses_silent_cache_when_available() -> None:
    """A cached account bypasses the device code flow."""

    flow = {"user_code": "ABCD1234"}
    token = {"access_token": "cached-token", "token_type": "Bearer"}
    client = _FakeClient(
        flow,
        token,
        accounts=[{"home_account_id": "abc"}],
        silent_response=token,
    )

    service = DeviceCodeLoginService(
        client_id="client-id",
        authority="https://login.microsoftonline.com/common",
        scopes=["scope/.default"],
        client=client,
        open_browser=False,
    )

    result = service.acquire_token()

    assert result == token
    assert client.initiated_with == []
    assert client.received_flow == []
