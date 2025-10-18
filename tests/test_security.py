"""Tests for security utilities."""
from __future__ import annotations

from cryptography.fernet import Fernet

from app.core import security
from app.core.config import reload_settings


def test_encrypt_decrypt_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", key)
    reload_settings()
    security.get_fernet.cache_clear()  # type: ignore[attr-defined]

    secret = "super-secret"
    encrypted = security.encrypt_str(secret)
    decrypted = security.decrypt_str(encrypted)

    assert decrypted == secret
