"""Authentication endpoints."""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decrypt_str,
    scopes_to_string,
)
from app.db import models
from app.db.base import get_db
from app.schemas.auth import TokenRequestPassword, TokenResponse


password_router = APIRouter(prefix="/auth", tags=["auth-password"])
client_router = APIRouter(prefix="/auth", tags=["auth-client"])


async def _extract_password_payload(request: Request) -> Dict[str, Any]:
    """Parse request body supporting JSON or form data for password logins."""

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Invalid payload")
        return data
    if "application/x-www-form-urlencoded" in content_type:
        body_bytes = await request.body()
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            body_str = body_bytes.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=400, detail="Invalid form encoding") from exc
        return {key: value for key, value in parse_qsl(body_str, keep_blank_values=True)}

    form = await request.form()
    return {key: value for key, value in form.multi_items()}


PASSWORD_REQUEST_BODY = {
    "required": True,
    "content": {
        media_type: {
            "schema": TokenRequestPassword.model_json_schema(),
        }
        for media_type in (
            "application/json",
            "application/x-www-form-urlencoded",
        )
    },
}


@password_router.post(
    "/token",
    response_model=TokenResponse,
    openapi_extra={"requestBody": PASSWORD_REQUEST_BODY},
)
async def obtain_token_with_password(
    request: Request, db: Session = Depends(get_db)
) -> TokenResponse:
    """Return an access token for email/password authentication."""

    payload = await _extract_password_payload(request)
    data = TokenRequestPassword(**payload)

    user = db.query(models.User).filter(models.User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    stored_password = decrypt_str(user.password_encrypted)
    if stored_password != data.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    settings = get_settings()
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


@client_router.get("/token", response_model=TokenResponse)
def obtain_token_with_client_credentials(
    *,
    client_id: str = Query(..., description="Client identifier"),
    client_secret: str = Query(..., description="Client secret"),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Return an access token for registered client credentials."""

    client = (
        db.query(models.ClientApp)
        .filter(models.ClientApp.client_id == client_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=400, detail="Invalid client credentials")

    stored_secret = decrypt_str(client.client_secret_encrypted)
    if stored_secret != client_secret:
        raise HTTPException(status_code=400, detail="Invalid client credentials")

    settings = get_settings()
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


__all__ = ["password_router", "client_router"]
