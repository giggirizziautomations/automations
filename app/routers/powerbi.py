"""Endpoints for interacting with Power BI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.db import models
from app.schemas import DeviceTokenResponse
from app.services import DeviceCodeLoginError, DeviceCodeLoginService


router = APIRouter(prefix="/powerbi", tags=["powerbi"])


def _resolve_authority(tenant: str) -> str:
    """Translate a tenant identifier or URL into an MSAL authority."""

    tenant = tenant.strip()
    if tenant.startswith("http://") or tenant.startswith("https://"):
        return tenant.rstrip("/")
    return f"https://login.microsoftonline.com/{tenant}"


def get_device_login_service(
    user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DeviceCodeLoginService:
    """Construct a device login service using per-user configuration."""

    tenant_id = (user.aad_tenant_id or settings.aad_tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Tenant ID is not configured for this user",
        )

    client_id = (user.aad_public_client_id or settings.msal_client_id or "").strip()
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="MSAL client ID is not configured",
        )

    if not settings.msal_scopes:
        raise HTTPException(
            status_code=500,
            detail="MSAL scopes are not configured",
        )

    token_cache_path = user.aad_token_cache_path or settings.msal_token_cache_path

    return DeviceCodeLoginService(
        client_id=client_id,
        authority=_resolve_authority(tenant_id),
        scopes=settings.msal_scopes,
        open_browser=settings.msal_open_browser,
        token_cache_path=token_cache_path,
    )


@router.post("/device-login", response_model=DeviceTokenResponse)
async def start_device_login(
    service: DeviceCodeLoginService = Depends(get_device_login_service),
) -> DeviceTokenResponse:
    """Start a device code flow and return the resulting token."""

    try:
        token_data = await run_in_threadpool(service.acquire_token)
    except DeviceCodeLoginError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DeviceTokenResponse.model_validate(token_data)


__all__ = ["router"]
