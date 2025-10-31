"""Pydantic models describing the Power BI service payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, StringConstraints


class PowerBIConfigRequest(BaseModel):
    """Payload used to configure the Power BI integration."""

    report_url: AnyHttpUrl = Field(description="Public URL of the Power BI report")
    export_format: Literal["csv", "xlsx", "json"] = Field(
        default="csv", description="Format used when exporting the report"
    )
    merge_strategy: Literal["append", "replace"] = Field(
        default="append", description="Strategy used when merging downloaded data"
    )
    username: str | None = Field(
        default=None,
        description="Optional username used to authenticate against Power BI",
    )
    password: str | None = Field(
        default=None,
        description=(
            "Optional password used to authenticate. If omitted the previous value "
            "is preserved."
        ),
    )


class PowerBIConfigResponse(BaseModel):
    """Represents the stored configuration for the Power BI integration."""

    id: int
    report_url: AnyHttpUrl
    export_format: Literal["csv", "xlsx", "json"]
    merge_strategy: Literal["append", "replace"]
    username: str | None
    has_password: bool
    created_at: datetime
    updated_at: datetime


VinStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
]


class PowerBIRunRequest(BaseModel):
    """Request body when triggering a Power BI export routine."""

    vin: VinStr = Field(description="VIN used to scope the exported data")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional parameters applied during the export",
    )
    notes: str | None = Field(
        default=None, description="Free form notes stored alongside the export"
    )


class PowerBIExportResponse(BaseModel):
    """Detailed representation of a stored Power BI export."""

    id: int
    vin: str
    status: str
    export_format: str
    report_url: AnyHttpUrl
    payload: dict[str, Any]
    notes: str | None
    created_at: datetime
    merged_at: datetime
    updated_at: datetime


__all__ = [
    "PowerBIConfigRequest",
    "PowerBIConfigResponse",
    "PowerBIRunRequest",
    "PowerBIExportResponse",
]
