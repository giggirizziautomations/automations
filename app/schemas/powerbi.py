"""Schemas related to Power BI integrations."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class DeviceCodeInitiationResponse(BaseModel):
    """Information required for completing the device code authentication."""

    flow_id: str = Field(description="Identifier for the initiated flow")
    user_code: str | None = Field(
        default=None, description="Code the user must enter on the verification page"
    )
    verification_uri: str | None = Field(
        default=None,
        description="Verification URL where the user should enter the code",
    )
    verification_uri_complete: str | None = Field(
        default=None,
        description="Verification URL with the user code embedded for convenience",
    )
    message: str | None = Field(
        default=None,
        description="Human-readable instructions returned by Azure AD",
    )
    expires_in: int | None = Field(
        default=None, description="Seconds until the device code expires"
    )
    interval: int | None = Field(
        default=None,
        description="Recommended polling interval for the device flow in seconds",
    )


class DeviceCodeCompleteRequest(BaseModel):
    """Payload used to finalise the device code flow."""

    flow_id: str = Field(description="Identifier previously returned by initiation")


__all__ = [
    "DeviceCodeCompleteRequest",
    "DeviceCodeInitiationResponse",
    "DeviceTokenResponse",
]
