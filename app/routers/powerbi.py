"""Endpoints for interacting with Power BI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.auth import get_current_user, require_admin_or_scopes
from app.core.config import Settings, get_settings
from app.db import models
from app.schemas import DeviceTokenResponse
from app.services import (
    DeviceCodeLoginError,
    DeviceCodeLoginService,
    PlaywrightDeviceLoginAutomation,
)


router = APIRouter(prefix="/powerbi", tags=["powerbi"])


def _resolve_authority(tenant: str) -> str:
    """Translate a tenant identifier or URL into an MSAL authority."""

    tenant = tenant.strip()
    if tenant.startswith("http://") or tenant.startswith("https://"):
        return tenant.rstrip("/")
    return f"https://login.microsoftonline.com/{tenant}"


def _build_device_login_service(
    *, user: models.User, settings: Settings, open_browser: bool | None = None
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

    if open_browser is None:
        open_browser = settings.msal_open_browser

    return DeviceCodeLoginService(
        client_id=client_id,
        authority=_resolve_authority(tenant_id),
        scopes=settings.msal_scopes,
        open_browser=open_browser,
        token_cache_path=token_cache_path,
    )


def get_playwright_device_automation(
    user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PlaywrightDeviceLoginAutomation:
    """FastAPI dependency providing a Playwright-assisted device login runner."""

    service = _build_device_login_service(
        user=user,
        settings=settings,
        open_browser=False,
    )
    return PlaywrightDeviceLoginAutomation(service=service)


@router.post(
    "/device-login",
    response_model=DeviceTokenResponse,
    dependencies=[Depends(require_admin_or_scopes(["bi-user"]))],
)
async def playwright_device_login(
    automation: PlaywrightDeviceLoginAutomation = Depends(
        get_playwright_device_automation
    ),
) -> DeviceTokenResponse:
    """Execute the device flow by driving a Playwright browser session."""

    try:
        token_data = await run_in_threadpool(automation.authenticate)
    except DeviceCodeLoginError as exc:
        detail: dict[str, object] = {
            "error": "device_login_failed",
            "message": str(exc) or "Device login failed for an unknown reason",
        }
        if exc.__cause__:
            detail["cause"] = repr(exc.__cause__)
        raise HTTPException(status_code=502, detail=detail) from exc

    return DeviceTokenResponse.model_validate(dict(token_data))


__all__ = ["router"]
