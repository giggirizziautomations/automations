"""Authentication and authorization dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token, normalize_scopes
from app.db.base import get_db
from app.db import models


security_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Represents the authenticated caller."""

    sub: str
    scopes: List[str]
    is_admin: bool
    user_id: Optional[int] = None
    client_id: Optional[str] = None


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Principal:
    """Return the authenticated principal based on the bearer token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials)
    sub = payload.get("sub")
    scopes = normalize_scopes(payload.get("scopes"))
    is_admin = bool(payload.get("is_admin", False))

    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    principal = _build_principal(sub=sub, scopes=scopes, is_admin=is_admin, db=db)
    return principal


def _build_principal(
    *, sub: str, scopes: List[str], is_admin: bool, db: Session
) -> Principal:
    """Create a principal instance from persisted entities."""

    user_id: Optional[int] = None
    client_id: Optional[str] = None

    if sub.isdigit():
        user = db.query(models.User).filter(models.User.id == int(sub)).first()
        if user:
            user_id = user.id
            scopes = normalize_scopes(user.scopes)
            is_admin = user.is_admin
            return Principal(
                sub=str(user.id),
                scopes=scopes,
                is_admin=is_admin,
                user_id=user.id,
            )

    client = (
        db.query(models.ClientApp).filter(models.ClientApp.client_id == sub).first()
    )
    if client:
        client_id = client.client_id
        scopes = normalize_scopes(client.scopes)
        return Principal(
            sub=client_id,
            scopes=scopes,
            is_admin=is_admin,
            client_id=client_id,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unknown authentication subject",
    )


async def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    """Ensure that the current principal has administrative rights."""

    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return principal


def require_scopes(required_scopes: Iterable[str]):
    """Create a dependency enforcing that the principal possesses scopes."""

    required = normalize_scopes(list(required_scopes))

    async def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        principal_scopes = set(principal.scopes)
        if principal.is_admin and "*" in principal_scopes:
            return principal
        missing = [scope for scope in required if scope not in principal_scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {' '.join(missing)}",
            )
        return principal

    return dependency


async def get_current_user(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> models.User:
    """Retrieve the current user entity for user principals."""

    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User context required",
        )
    user = db.query(models.User).filter(models.User.id == principal.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


__all__ = [
    "Principal",
    "get_current_principal",
    "get_current_user",
    "require_admin",
    "require_scopes",
]
