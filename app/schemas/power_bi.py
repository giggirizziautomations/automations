"""Pydantic models describing the Power BI service payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, StringConstraints

from app.schemas.scraping import ScrapingAction


class PowerBIConfigRequest(BaseModel):
    """Payload used to configure the Power BI integration."""

    config_id: int | None = Field(
        default=None,
        description="Identifier of the configuration to update. Omit to create a new one.",
    )
    report_url: AnyHttpUrl = Field(description="Public URL of the Power BI report")
    export_format: Literal["csv", "xlsx", "json"] = Field(
        default="xlsx", description="Format used when exporting the report"
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
    scraping_actions: list[ScrapingAction] = Field(
        default_factory=list,
        description=(
            "Actions executed by the scraping engine before downloading the report."
        ),
    )


class PowerBIConfigResponse(BaseModel):
    """Represents the stored configuration for the Power BI integration."""

    id: int
    user_id: int
    report_url: AnyHttpUrl
    export_format: Literal["csv", "xlsx", "json"]
    merge_strategy: Literal["append", "replace"]
    username: str | None
    has_password: bool
    scraping_actions: list[ScrapingAction]
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
    routine_id: int = Field(
        description="Identifier of the scraping routine to execute before export"
    )
    dedup_parameter: str = Field(
        description="Name of the field used to deduplicate merged rows",
        min_length=1,
    )
    datasets: list[list[dict[str, Any]]] = Field(
        default_factory=list,
        description=(
            "Rows extracted from downloaded spreadsheets. Each inner list represents "
            "a single file."
        ),
    )


class PowerBIScrapingRoutineRequest(BaseModel):
    """Request body when associating a scraping routine with the Power BI config."""

    config_id: int = Field(
        description="Identifier of the Power BI configuration receiving the actions"
    )
    routine_id: int = Field(
        description="Identifier of the scraping routine containing the actions"
    )


class PowerBIExportResponse(BaseModel):
    """Detailed representation of a stored Power BI export."""

    id: int
    config_id: int
    routine_id: int
    vin: str
    status: str
    export_format: str
    report_url: AnyHttpUrl
    dedup_parameter: str
    payload: dict[str, Any]
    notes: str | None
    created_at: datetime
    merged_at: datetime
    updated_at: datetime


class PowerBIMergedRow(BaseModel):
    """Representation of a merged dataset row stored in DuckDB."""

    export_id: int
    routine_id: int
    config_id: int
    dedup_parameter: str
    parameter_value: str
    data: dict[str, Any]


__all__ = [
    "PowerBIConfigRequest",
    "PowerBIConfigResponse",
    "PowerBIRunRequest",
    "PowerBIExportResponse",
    "PowerBIScrapingRoutineRequest",
    "PowerBIMergedRow",
]
