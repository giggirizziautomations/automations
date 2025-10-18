"""Authentication endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decrypt_str,
    scopes_to_string,
)
from app.db import models
from app.db.base import get_db
from app.schemas.auth import (
    TokenRequestClient,
    TokenRequestPassword,
    TokenResponse,
)


router = APIRouter(prefix="/auth", tags=["auth"])


async def _extract_payload(request: Request) -> Dict[str, Any]:
    """Parse request body supporting JSON or form data."""

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Invalid payload")
        return data
    form = await request.form()
    return {key: value for key, value in form.multi_items()}


@router.post("/token", response_model=TokenResponse)
async def obtain_token(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    """Return an access token for either user password or client credentials."""

    payload = await _extract_payload(request)
    grant_type = payload.get("grant_type")

    settings = get_settings()

    if grant_type == "password":
        data = TokenRequestPassword(**payload)
        user = (
            db.query(models.User).filter(models.User.email == data.email).first()
        )
        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        stored_password = decrypt_str(user.password_encrypted)
        if stored_password != data.password:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        scopes = user.get_scopes()
        token = create_access_token(
            sub=str(user.id),
            scopes=scopes,
            is_admin=user.is_admin,
            expires_minutes=settings.access_token_expire_minutes,
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            scope=scopes_to_string(scopes),
        )

    if grant_type == "client_credentials":
        data = TokenRequestClient(**payload)
        client = (
            db.query(models.ClientApp)
            .filter(models.ClientApp.client_id == data.client_id)
            .first()
        )
        if not client:
            raise HTTPException(status_code=400, detail="Invalid client credentials")
        stored_secret = decrypt_str(client.client_secret_encrypted)
        if stored_secret != data.client_secret:
            raise HTTPException(status_code=400, detail="Invalid client credentials")
        scopes = client.get_scopes()
        token = create_access_token(
            sub=client.client_id,
            scopes=scopes,
            is_admin=False,
            expires_minutes=settings.access_token_expire_minutes,
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            scope=scopes_to_string(scopes),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported grant type",
    )
