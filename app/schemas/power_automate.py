"""Pydantic schemas for Power Automate flow management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class PowerAutomateFlowBase(BaseModel):
    """Shared attributes describing a Power Automate flow."""

    name: str = Field(..., min_length=1, max_length=255)
    url: HttpUrl
    method: HttpMethod = "POST"
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)


class PowerAutomateFlowRequest(PowerAutomateFlowBase):
    """Payload used to create or update a flow configuration."""

    model_config = ConfigDict(extra="forbid")


class PowerAutomateFlowResponse(PowerAutomateFlowBase):
    """Representation of a stored Power Automate flow."""

    id: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PowerAutomateInvocationRequest(BaseModel):
    """Parameters supplied when invoking a Power Automate flow."""

    parameters: dict[str, Any] = Field(default_factory=dict)
    body_overrides: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    wait_for_completion: bool = True
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    failure_flow_id: int | None = None
    failure_parameters: dict[str, Any] = Field(default_factory=dict)
    failure_body_overrides: dict[str, Any] = Field(default_factory=dict)
    failure_query_params: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class PowerAutomateInvocationResponse(BaseModel):
    """Structured response returned after invoking a flow."""

    flow_id: int
    status: Literal["success", "timeout", "error"]
    http_status: int | None = None
    response: Any | None = None
    detail: str | None = None
    failure_flow_triggered: bool = False

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "PowerAutomateFlowRequest",
    "PowerAutomateFlowResponse",
    "PowerAutomateInvocationRequest",
    "PowerAutomateInvocationResponse",
    "HttpMethod",
]
