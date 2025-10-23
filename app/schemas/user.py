"""User related schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    name: str = Field(..., max_length=100)
    surname: str = Field(..., max_length=100)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    scopes: Optional[list[str]] = Field(default=None)
    is_admin: bool = Field(default=False)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    surname: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6)
    scopes: Optional[list[str]] = None
    is_admin: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    name: str
    surname: str
    email: EmailStr
    scopes: list[str]
    is_admin: bool

    model_config = {
        "from_attributes": True,
    }
