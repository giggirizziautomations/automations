"""Endpoints to manage scraping target configurations."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from sqlalchemy.orm import Session

from app.core.auth import Principal, require_admin
from app.db import models
from app.db.base import get_db
from app.schemas.scraping import (
    ScrapingActionDocument,
    ScrapingActionPayload,
    ScrapingActionsUpdate,
    ScrapingTargetCreate,
    ScrapingTargetOut,
)
from app.scraping.helpers import build_action_step, build_actions_document


router = APIRouter(prefix="/scraping-targets", tags=["scraping"])


def _serialize_target(target: models.ScrapingTarget) -> ScrapingTargetOut:
    return ScrapingTargetOut(
        id=target.id,
        user_id=target.user_id,
        site_name=target.site_name,
        url=target.url,
        recipe=target.recipe,
        parameters=json.loads(target.parameters or "{}"),
        notes=target.notes,
        has_password=bool(target.password_encrypted),
    )


@router.post("", response_model=ScrapingTargetOut, status_code=status.HTTP_201_CREATED)
async def create_scraping_target(
    payload: ScrapingTargetCreate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Create a scraping target for the specified user."""

    existing = (
        db.query(models.ScrapingTarget)
        .filter(
            models.ScrapingTarget.user_id == payload.user_id,
            models.ScrapingTarget.site_name == payload.site_name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scraping target already exists for this user and site",
        )

    parameters_json = json.dumps(payload.parameters or {})
    notes_value = (payload.notes or "").strip()

    target = models.ScrapingTarget(
        user_id=payload.user_id,
        site_name=payload.site_name,
        url=payload.url,
        recipe=(payload.recipe or "default").strip() or "default",
        parameters=parameters_json,
        notes=notes_value,
    )
    target.set_password(payload.password)

    db.add(target)
    db.commit()
    db.refresh(target)

    return _serialize_target(target)


@router.put("/{target_id}/actions", response_model=ScrapingTargetOut)
async def update_scraping_target_actions(
    target_id: int,
    payload: ScrapingActionsUpdate,
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Replace the JSON actions document stored for ``target_id``."""

    target = (
        db.query(models.ScrapingTarget)
        .filter(models.ScrapingTarget.id == target_id)
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraping target not found",
        )

    current_parameters = json.loads(target.parameters or "{}")
    if payload.parameters:
        current_parameters.update(payload.parameters)

    current_parameters["actions"] = [
        step.model_dump(exclude_none=True) for step in payload.actions
    ]

    target.parameters = json.dumps(current_parameters)
    db.add(target)
    db.commit()
    db.refresh(target)

    return _serialize_target(target)


def _coerce_qs_values(data: dict[str, list[str]]) -> dict[str, object]:
    coerced: dict[str, object] = {}
    for key, values in data.items():
        if not values:
            continue
        if len(values) == 1:
            coerced[key] = values[0]
        else:
            coerced[key] = values
    return coerced


def _repair_html_quotes(raw_body: str) -> str:
    """Escape unencoded quotes inside the ``html`` attribute if present."""

    pattern = re.compile(r'("html"\s*:\s*")(?P<html>.*?)(?<!\\)"(?=\s*(,|}))', re.DOTALL)

    def _replacer(match: re.Match[str]) -> str:
        escaped = match.group("html").replace("\\", "\\\\").replace('"', '\\"')
        return f'{match.group(1)}{escaped}"'

    return pattern.sub(_replacer, raw_body, count=1)


def _parse_multipart_form_data(raw_body: bytes, *, boundary: str) -> dict[str, list[str]]:
    """Parse a multipart form payload keeping only textual fields."""

    boundary = boundary.strip().strip('"')
    if not boundary:
        return {}

    delimiter = f"--{boundary}".encode("utf-8", errors="ignore")
    parts = raw_body.split(delimiter)

    items: dict[str, list[str]] = {}
    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2]
        part = part.strip(b"\r\n")
        headers_blob, _, value_blob = part.partition(b"\r\n\r\n")
        if not value_blob:
            continue

        headers = headers_blob.decode("utf-8", errors="ignore").split("\r\n")
        disposition = next(
            (header for header in headers if header.lower().startswith("content-disposition")),
            None,
        )
        if not disposition:
            continue

        name_match = re.search(r'name="(?P<name>[^"]+)"', disposition)
        if not name_match:
            continue
        if re.search(r'filename="', disposition):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File uploads are not supported for this endpoint",
            )

        value_text = value_blob.rstrip(b"\r\n").decode("utf-8", errors="ignore")
        items.setdefault(name_match.group("name"), []).append(value_text)

    return items


async def _parse_action_payload(request: Request) -> ScrapingActionPayload:
    raw_bytes = await request.body()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body is required",
        )

    data: dict[str, object] | None = None
    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:
        boundary_match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
        if boundary_match:
            form_items = _parse_multipart_form_data(
                raw_bytes, boundary=boundary_match.group("boundary")
            )
            if form_items:
                data = _coerce_qs_values(form_items)
    elif "application/x-www-form-urlencoded" in content_type:
        parsed_qs = parse_qs(raw_bytes.decode("utf-8", errors="ignore"))
        if parsed_qs:
            data = _coerce_qs_values(parsed_qs)

    if data is None:
        body_text = raw_bytes.decode("utf-8", errors="ignore")

        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            try:
                repaired = _repair_html_quotes(body_text)
                data = json.loads(repaired)
            except json.JSONDecodeError:
                parsed_qs = parse_qs(body_text)
                if parsed_qs:
                    data = _coerce_qs_values(parsed_qs)

    if data is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid request payload; expected JSON object",
        )

    if isinstance(data, dict) and "payload" in data:
        raw_payload = data["payload"]
        if isinstance(raw_payload, str):
            try:
                payload_data = json.loads(raw_payload)
            except json.JSONDecodeError as exc:  # noqa: PERF203
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid payload; expected JSON object",
                ) from exc
        elif isinstance(raw_payload, dict):
            payload_data = raw_payload
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid payload; expected JSON object",
            )

        recognised_keys = {"html", "action", "suggestion", "value", "settle_ms"}
        overrides = {
            key: value
            for key, value in data.items()
            if key in recognised_keys and key != "payload"
        }
        data = {**payload_data, **overrides}

    try:
        return ScrapingActionPayload.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(errors=exc.errors()) from exc


@router.post("/actions/preview", response_model=ScrapingActionDocument)
async def preview_scraping_action(
    payload: ScrapingActionPayload = Depends(_parse_action_payload),
    _: Principal = Depends(require_admin),
) -> ScrapingActionDocument:
    """Render a scraping action document from the provided HTML snippet."""

    document = build_actions_document(
        payload.html,
        payload.action,
        value=payload.value,
        settle_ms=payload.settle_ms,
    )
    return ScrapingActionDocument(**document)


@router.post("/{target_id}/actions/from-html", response_model=ScrapingTargetOut)
async def append_scraping_action_from_html(
    target_id: int,
    payload: ScrapingActionPayload = Depends(_parse_action_payload),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> ScrapingTargetOut:
    """Append a generated scraping action to the stored configuration."""

    target = (
        db.query(models.ScrapingTarget)
        .filter(models.ScrapingTarget.id == target_id)
        .first()
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraping target not found",
        )

    current_parameters = json.loads(target.parameters or "{}")
    actions: list[dict[str, object]] = []
    existing_actions = current_parameters.get("actions")
    if isinstance(existing_actions, list):
        actions.extend(
            step
            for step in existing_actions
            if isinstance(step, dict)
        )

    new_action = build_action_step(payload.html, payload.action, value=payload.value)
    actions.append(new_action)
    current_parameters["actions"] = actions

    if payload.settle_ms is not None:
        current_parameters["settle_ms"] = payload.settle_ms

    target.parameters = json.dumps(current_parameters)
    db.add(target)
    db.commit()
    db.refresh(target)

    return _serialize_target(target)


__all__ = ["router"]
