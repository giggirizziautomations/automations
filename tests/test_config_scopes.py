"""Tests for MSAL scope configuration parsing."""

from app.core import config


def _clear_env(monkeypatch):
    monkeypatch.delenv("SCOPES", raising=False)
    monkeypatch.delenv("MSAL_SCOPES", raising=False)


def test_legacy_csv_scopes_supports_commas(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(
        "MSAL_SCOPES",
        "https://example.crm.dynamics.com/user_impersonation,offline_access,openid",
    )

    try:
        settings = config.reload_settings()
        assert settings.msal_scopes == (
            "https://example.crm.dynamics.com/user_impersonation",
            "offline_access",
            "openid",
        )
    finally:
        _clear_env(monkeypatch)
        config.reload_settings()


def test_legacy_csv_scopes_supports_whitespace(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(
        "MSAL_SCOPES",
        "https://example.crm.dynamics.com/user_impersonation offline_access openid",
    )

    try:
        settings = config.reload_settings()
        assert settings.msal_scopes == (
            "https://example.crm.dynamics.com/user_impersonation",
            "offline_access",
            "openid",
        )
    finally:
        _clear_env(monkeypatch)
        config.reload_settings()
