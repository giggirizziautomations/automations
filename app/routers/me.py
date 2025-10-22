"""Endpoints for the authenticated user's profile."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.security import encrypt_str
from app.db import models
from app.db.base import get_db
from app.schemas.user import UserOut


class MeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    surname: Optional[str] = Field(default=None, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6)


router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
async def get_me(user: models.User = Depends(get_current_user)) -> UserOut:
    """Return the authenticated user's profile."""

    return UserOut(
        id=user.id,
        name=user.name,
        surname=user.surname,
        email=user.email,
        scopes=user.get_scopes(),
        is_admin=user.is_admin,
        aad_tenant_id=user.aad_tenant_id,
        aad_public_client_id=user.aad_public_client_id,
        aad_token_cache_path=user.aad_token_cache_path,
    )


@router.patch("", response_model=UserOut)
async def update_me(
    payload: MeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update the current user's profile."""

    if payload.email and payload.email != user.email:
        exists = db.query(models.User).filter(models.User.email == payload.email).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email già registrata")
        user.email = payload.email

    if payload.name is not None:
        user.name = payload.name
    if payload.surname is not None:
        user.surname = payload.surname
    if payload.password is not None:
        user.password_encrypted = encrypt_str(payload.password)

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserOut(
        id=user.id,
        name=user.name,
        surname=user.surname,
        email=user.email,
        scopes=user.get_scopes(),
        is_admin=user.is_admin,
        aad_tenant_id=user.aad_tenant_id,
        aad_public_client_id=user.aad_public_client_id,
        aad_token_cache_path=user.aad_token_cache_path,
    )
