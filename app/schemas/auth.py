"""Authentication related schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(..., description="Expiration in seconds")
    scope: str = Field(..., description="Space separated scopes")


class TokenRequestPassword(BaseModel):
    grant_type: str = Field(default="password")
    email: str
    password: str
    scope: Optional[str] = None


class TokenRequestClient(BaseModel):
    grant_type: str = Field(default="client_credentials")
    client_id: str
    client_secret: str
    scope: Optional[str] = None
