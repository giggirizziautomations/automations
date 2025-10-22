"""Endpoints for interacting with Power BI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.schemas import DeviceTokenResponse
from app.services import DeviceCodeLoginError, DeviceCodeLoginService


router = APIRouter(prefix="/powerbi", tags=["powerbi"])


def get_device_login_service(
    settings: Settings = Depends(get_settings),
) -> DeviceCodeLoginService:
    """Construct a device login service from configuration."""

    if not settings.msal_client_id:
        raise HTTPException(
            status_code=500, detail="MSAL client ID is not configured"
        )
    if not settings.msal_scopes:
        raise HTTPException(
            status_code=500, detail="MSAL scopes are not configured"
        )

    return DeviceCodeLoginService(
        client_id=settings.msal_client_id,
        authority=settings.msal_authority,
        scopes=settings.msal_scopes,
        open_browser=settings.msal_open_browser,
        token_cache_path=settings.msal_token_cache_path,
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
