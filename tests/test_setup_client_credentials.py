"""Tests for client credential provisioning helpers."""
from __future__ import annotations

from app.core.security import decrypt_str
from app.db import models
from app.setup import client_credentials


def test_generate_client_secret_length() -> None:
    secret = client_credentials.generate_client_secret()

    assert isinstance(secret, str)
    assert len(secret) == 64


def test_create_client_application(db_session):
    client, secret = client_credentials.create_client_application(
        name="Analytics", client_id="analytics-service", scopes=["reports:read"]
    )

    assert client.id is not None
    assert client.client_id == "analytics-service"
    assert len(secret) == 64
    assert decrypt_str(client.client_secret_encrypted) == secret

    stored = (
        db_session.query(models.ClientApp)
        .filter(models.ClientApp.client_id == "analytics-service")
        .first()
    )
    assert stored is not None
    assert stored.get_scopes() == ["reports:read"]
