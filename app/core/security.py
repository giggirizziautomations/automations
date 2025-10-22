"""Security utilities for encryption, token management, and scopes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Iterable, List

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import get_settings


class SecurityError(RuntimeError):
    """Raised when critical security components are misconfigured."""


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    """Return a Fernet instance configured with the application key."""

    key = get_settings().fernet_key
    if not key:
        raise SecurityError("FERNET_KEY environment variable is not configured.")
    return Fernet(key.encode() if not isinstance(key, bytes) else key)


def encrypt_str(plain: str) -> str:
    """Encrypt a string value using Fernet."""

    token = get_fernet().encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_str(token: str) -> str:
    """Decrypt a Fernet token into its original string."""

    try:
        value = get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid encrypted data.",
        ) from exc
    return value.decode("utf-8")


def normalize_scopes(scopes: Iterable[str] | str | None) -> List[str]:
    """Normalise scopes from either an iterable or a space separated string."""

    if scopes is None:
        return []
    if isinstance(scopes, str):
        items = scopes.split()
    else:
        items = list(scopes)
    unique = sorted(set(scope.strip() for scope in items if scope.strip()))
    return unique


def scopes_to_string(scopes: Iterable[str]) -> str:
    """Serialise scopes for persistence."""

    return " ".join(sorted(set(scope for scope in scopes if scope)))


def create_access_token(
    *,
    sub: str,
    scopes: List[str],
    is_admin: bool,
    expires_minutes: int,
) -> str:
    """Create a signed JWT access token."""

    settings = get_settings()
    if not settings.jwt_secret:
        raise SecurityError("JWT_SECRET environment variable is not configured.")
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": sub,
        "scopes": scopes,
        "is_admin": is_admin,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode a JWT token and return its payload."""

    settings = get_settings()
    if not settings.jwt_secret:
        raise SecurityError("JWT_SECRET environment variable is not configured.")
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


__all__ = [
    "SecurityError",
    "create_access_token",
    "decode_token",
    "decrypt_str",
    "encrypt_str",
    "get_fernet",
    "normalize_scopes",
    "scopes_to_string",
]
