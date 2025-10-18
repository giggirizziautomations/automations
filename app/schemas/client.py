"""Client application schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(..., max_length=255)
    scopes: Optional[list[str]] = Field(default=None)


class ClientOut(BaseModel):
    client_id: str
    name: str
    scopes: list[str]

    model_config = {
        "from_attributes": True,
    }
