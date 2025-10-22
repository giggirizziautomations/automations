"""Administrative user management endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_user, require_admin
from app.core.config import get_settings
from app.core.security import encrypt_str
from app.db import models
from app.db.base import get_db
from app.schemas.user import UserCreate, UserOut, UserUpdate


router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> UserOut:
    """Create a new user."""

    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    settings = get_settings()
    user = models.User(
        name=payload.name,
        surname=payload.surname,
        email=payload.email,
        password_encrypted=encrypt_str(payload.password),
        is_admin=payload.is_admin,
        aad_tenant_id=payload.aad_tenant_id or settings.aad_tenant_id,
        aad_public_client_id=(
            payload.aad_public_client_id or settings.msal_client_id
        ),
        aad_token_cache_path=(
            payload.aad_token_cache_path or settings.msal_token_cache_path
        ),
    )
    user.set_scopes(payload.scopes or [])
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


@router.get("", response_model=List[UserOut])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> List[UserOut]:
    """List users with pagination."""

    users = db.query(models.User).offset(skip).limit(limit).all()
    return [
        UserOut(
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
        for user in users
    ]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> UserOut:
    """Retrieve a user by identifier."""

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
async def update_user(
    payload: UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """Update the authenticated user's information."""

    if payload.scopes is not None or payload.is_admin is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to modify administrative fields",
        )

    if payload.email and payload.email != user.email:
        exists = db.query(models.User).filter(models.User.email == payload.email).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")
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


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> Response:
    """Delete a user."""

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
