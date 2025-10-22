"""Endpoints for interacting with Power BI."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Mapping, MutableMapping

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.auth import get_current_user, require_admin_or_scopes
from app.core.config import Settings, get_settings
from app.db import models
from app.schemas import (
    DeviceCodeCompleteRequest,
    DeviceCodeInitiationResponse,
    DeviceTokenResponse,
)
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


def get_device_login_service(
    user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DeviceCodeLoginService:
    """FastAPI dependency that yields a configured login service."""

    return _build_device_login_service(user=user, settings=settings)


@dataclass
class _PendingFlow:
    """Stores an in-flight MSAL device flow."""

    owner_user_id: int
    service: DeviceCodeLoginService
    flow: MutableMapping[str, object]
    expires_at: float


_PENDING_DEVICE_FLOWS: dict[str, _PendingFlow] = {}
_PENDING_LOCK = threading.Lock()


def _generate_flow_id() -> str:
    return secrets.token_urlsafe(24)


def _register_pending_flow(
    *, user_id: int, service: DeviceCodeLoginService, flow: MutableMapping[str, object]
) -> str:
    """Persist flow metadata for later completion."""

    expires_in = flow.get("expires_in")
    try:
        ttl = int(expires_in)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        ttl = 900

    flow_id = _generate_flow_id()
    expires_at = time.monotonic() + max(ttl, 0)

    with _PENDING_LOCK:
        _purge_expired_flows_locked()
        _PENDING_DEVICE_FLOWS[flow_id] = _PendingFlow(
            owner_user_id=user_id,
            service=service,
            flow=flow,
            expires_at=expires_at,
        )

    return flow_id


def _purge_expired_flows_locked() -> None:
    """Remove flows that have exceeded their lifetime."""

    now = time.monotonic()
    expired = [
        flow_id
        for flow_id, pending in _PENDING_DEVICE_FLOWS.items()
        if pending.expires_at <= now
    ]
    for flow_id in expired:
        _PENDING_DEVICE_FLOWS.pop(flow_id, None)


def _pop_pending_flow(user_id: int, flow_id: str) -> _PendingFlow | None:
    """Retrieve and remove a pending flow for the given user."""

    with _PENDING_LOCK:
        pending = _PENDING_DEVICE_FLOWS.get(flow_id)
        if not pending or pending.owner_user_id != user_id:
            return None
        return _PENDING_DEVICE_FLOWS.pop(flow_id, None)


@router.post("/device-login", response_model=DeviceCodeInitiationResponse)
async def initiate_device_login(
    user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DeviceCodeInitiationResponse:
    """Start a device code flow and return instructions for completion."""

    service = _build_device_login_service(user=user, settings=settings)

    try:
        flow = await run_in_threadpool(service.initiate_device_flow)
    except DeviceCodeLoginError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    flow_id = _register_pending_flow(user_id=user.id, service=service, flow=flow)

    return DeviceCodeInitiationResponse(
        flow_id=flow_id,
        user_code=flow.get("user_code"),
        verification_uri=flow.get("verification_uri"),
        verification_uri_complete=flow.get("verification_uri_complete"),
        message=flow.get("message"),
        expires_in=flow.get("expires_in"),
        interval=flow.get("interval"),
    )


@router.post("/device-login/complete", response_model=DeviceTokenResponse)
async def complete_device_login(
    payload: DeviceCodeCompleteRequest,
    user: models.User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DeviceTokenResponse:
    """Complete a previously initiated device code flow."""

    pending = _pop_pending_flow(user.id, payload.flow_id)
    if not pending:
        # Re-run configuration validation to provide consistent errors
        _build_device_login_service(user=user, settings=settings)
        raise HTTPException(status_code=404, detail="Device code flow not found")

    try:
        token_data = await run_in_threadpool(
            pending.service.acquire_token_with_flow, pending.flow
        )
    except DeviceCodeLoginError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(token_data, Mapping):
        try:
            token_data = await run_in_threadpool(pending.service.acquire_token)
        except DeviceCodeLoginError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DeviceTokenResponse.model_validate(dict(token_data))


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
    "/device-login/playwright",
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
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DeviceTokenResponse.model_validate(dict(token_data))


__all__ = ["router"]
