"""Schemas related to Power BI integrations."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DeviceTokenResponse(BaseModel):
    """Access token returned after completing the device code flow."""

    token_type: str | None = None
    expires_in: int | None = None
    ext_expires_in: int | None = None
    expires_on: int | None = None
    scope: str | None = None
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None

    model_config = ConfigDict(extra="ignore")

__all__ = [
    "DeviceTokenResponse",
]
