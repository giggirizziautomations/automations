"""Service layer for managing and invoking Power Automate flows."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from sqlalchemy.orm import Session

from app.db import models
from app.schemas.power_automate import (
    PowerAutomateFlowRequest,
    PowerAutomateFlowResponse,
    PowerAutomateInvocationRequest,
    PowerAutomateInvocationResponse,
)

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


@dataclass(slots=True)
class PowerAutomateInvocationResult:
    """Internal representation of a flow execution."""

    flow_id: int
    status: str
    http_status: int | None
    response: Any | None
    detail: str | None
    failure_flow_triggered: bool


def _serialise_flow(flow: models.PowerAutomateFlow) -> PowerAutomateFlowResponse:
    timeout = flow.timeout_seconds or 1800
    return PowerAutomateFlowResponse(
        id=flow.id,
        name=flow.name,
        url=flow.url,
        method=flow.method.upper(),
        timeout_seconds=timeout,
        headers=dict(flow.headers or {}),
        body_template=dict(flow.body_template or {}),
        created_at=flow.created_at,
        updated_at=flow.updated_at,
    )


def _lookup(data: Any, path: str) -> Any:
    """Return the value referenced by ``path`` using dotted notation."""

    current = data
    for chunk in path.split("."):
        chunk = chunk.strip()
        if not chunk:
            return None
        if isinstance(current, dict):
            current = current.get(chunk)
        elif isinstance(current, (list, tuple)):
            try:
                index = int(chunk)
            except ValueError:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def render_template(template: Any, variables: dict[str, Any]) -> Any:
    """Recursively interpolate placeholders in ``template`` using ``variables``."""

    if isinstance(template, str):
        matches: list[re.Match[str]] = list(_PLACEHOLDER_PATTERN.finditer(template))
        if not matches:
            return template

        def resolve_expression(expression: str) -> Any:
            expression = expression.strip()
            return _lookup(variables, expression)

        def replacer(match: re.Match[str]) -> str:
            expression = match.group(1).strip()
            value = _lookup(variables, expression)
            if value is None:
                return match.group(0)
            return str(value)

        if len(matches) == 1 and matches[0].group(0) == template:
            value = resolve_expression(matches[0].group(1))
            if value is None:
                return template
            return value

        return _PLACEHOLDER_PATTERN.sub(replacer, template)

    if isinstance(template, dict):
        return {key: render_template(value, variables) for key, value in template.items()}

    if isinstance(template, list):
        return [render_template(item, variables) for item in template]

    return template


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def list_flows(*, db: Session, user_id: int) -> list[PowerAutomateFlowResponse]:
    flows = (
        db.query(models.PowerAutomateFlow)
        .filter(models.PowerAutomateFlow.user_id == user_id)
        .order_by(models.PowerAutomateFlow.created_at.asc())
        .all()
    )
    return [_serialise_flow(flow) for flow in flows]


def _resolve_timeout(payload: PowerAutomateFlowRequest | PowerAutomateInvocationRequest, default: int) -> int:
    value = payload.timeout_seconds if payload.timeout_seconds is not None else default
    return max(1, min(value, 1800))


def create_flow(*, db: Session, user_id: int, payload: PowerAutomateFlowRequest) -> PowerAutomateFlowResponse:
    timeout = _resolve_timeout(payload, 1800)
    flow = models.PowerAutomateFlow(
        user_id=user_id,
        name=payload.name,
        url=str(payload.url),
        method=payload.method.upper(),
        timeout_seconds=timeout,
        headers=dict(payload.headers or {}),
        body_template=dict(payload.body_template or {}),
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return _serialise_flow(flow)


def _get_flow(*, db: Session, user_id: int, flow_id: int) -> models.PowerAutomateFlow:
    flow = (
        db.query(models.PowerAutomateFlow)
        .filter(
            models.PowerAutomateFlow.id == flow_id,
            models.PowerAutomateFlow.user_id == user_id,
        )
        .first()
    )
    if not flow:
        raise LookupError("Flow not found")
    return flow


def update_flow(
    *,
    db: Session,
    user_id: int,
    flow_id: int,
    payload: PowerAutomateFlowRequest,
) -> PowerAutomateFlowResponse:
    flow = _get_flow(db=db, user_id=user_id, flow_id=flow_id)
    timeout = _resolve_timeout(payload, flow.timeout_seconds or 1800)
    flow.name = payload.name
    flow.url = str(payload.url)
    flow.method = payload.method.upper()
    flow.timeout_seconds = timeout
    flow.headers = dict(payload.headers or {})
    flow.body_template = dict(payload.body_template or {})
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return _serialise_flow(flow)


def delete_flow(*, db: Session, user_id: int, flow_id: int) -> None:
    flow = _get_flow(db=db, user_id=user_id, flow_id=flow_id)
    db.delete(flow)
    db.commit()


def _prepare_request_payload(
    *,
    flow: models.PowerAutomateFlow,
    invocation: PowerAutomateInvocationRequest,
    variables: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any] | None, dict[str, Any]]:
    headers = {str(key): str(value) for key, value in (flow.headers or {}).items()}
    rendered_body = render_template(flow.body_template or {}, variables)
    rendered_query = render_template(invocation.query_params or {}, variables)
    body_overrides = render_template(invocation.body_overrides or {}, variables)
    merged_body = _deep_merge(rendered_body, body_overrides) if rendered_body or body_overrides else body_overrides
    if not merged_body:
        json_payload = None
    else:
        json_payload = merged_body
    return headers, json_payload, rendered_query


@asynccontextmanager
async def _get_async_client(timeout_seconds: int) -> AsyncIterator[httpx.AsyncClient]:
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        yield client


async def _dispatch_request(
    *,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    json_payload: dict[str, Any] | None,
    query: dict[str, Any],
    wait_for_completion: bool,
) -> tuple[int | None, Any | None, str | None]:
    try:
        response = await client.request(
            method,
            url,
            headers=headers,
            json=json_payload,
            params=query or None,
        )
        if not wait_for_completion:
            return response.status_code, None, None
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body = response.json()
        elif response.content:
            try:
                body = response.json()
            except ValueError:
                body = response.text
        else:
            body = None
        return response.status_code, body, None
    except httpx.TimeoutException:
        logger.warning("Power Automate flow timed out")
        return None, None, "timeout"
    except httpx.HTTPError as exc:  # pragma: no cover - network layer defensive guard
        logger.exception("Power Automate flow failed")
        return None, None, str(exc)


async def invoke_flow(
    *,
    db: Session,
    user_id: int,
    flow_id: int,
    payload: PowerAutomateInvocationRequest,
    template_variables: dict[str, Any] | None = None,
    _trigger_failure: bool = True,
) -> PowerAutomateInvocationResult:
    flow = _get_flow(db=db, user_id=user_id, flow_id=flow_id)
    timeout = payload.timeout_seconds or flow.timeout_seconds or 1800
    timeout = max(1, min(timeout, 1800))

    variables: dict[str, Any] = {
        "parameters": payload.parameters or {},
    }
    variables.update(payload.parameters or {})
    if template_variables:
        variables.update(template_variables)

    headers, json_payload, query = _prepare_request_payload(
        flow=flow,
        invocation=payload,
        variables=variables,
    )

    async with _get_async_client(timeout) as client:
        status_code, body, error = await _dispatch_request(
            client=client,
            method=flow.method,
            url=flow.url,
            headers=headers,
            json_payload=json_payload,
            query=query,
            wait_for_completion=payload.wait_for_completion,
        )

    failure_triggered = False
    detail: str | None = None
    result_status = "success"
    response_body = body

    if error == "timeout":
        result_status = "timeout"
        detail = "Flow execution timed out"
    elif error:
        result_status = "error"
        detail = error
    elif status_code is not None and status_code >= 400:
        result_status = "error"
        detail = f"Flow returned status {status_code}"

    if result_status != "success" and payload.failure_flow_id and _trigger_failure:
        failure_triggered = True
        failure_payload = PowerAutomateInvocationRequest(
            parameters=payload.failure_parameters,
            body_overrides=payload.failure_body_overrides,
            query_params=payload.failure_query_params,
            wait_for_completion=False,
            timeout_seconds=min(timeout, 600),
        )
        await invoke_flow(
            db=db,
            user_id=user_id,
            flow_id=payload.failure_flow_id,
            payload=failure_payload,
            template_variables=template_variables,
            _trigger_failure=False,
        )

    return PowerAutomateInvocationResult(
        flow_id=flow_id,
        status=result_status,
        http_status=status_code,
        response=response_body,
        detail=detail,
        failure_flow_triggered=failure_triggered,
    )


def to_schema(result: PowerAutomateInvocationResult) -> PowerAutomateInvocationResponse:
    return PowerAutomateInvocationResponse(
        flow_id=result.flow_id,
        status=result.status,
        http_status=result.http_status,
        response=result.response,
        detail=result.detail,
        failure_flow_triggered=result.failure_flow_triggered,
    )


__all__ = [
    "create_flow",
    "list_flows",
    "update_flow",
    "delete_flow",
    "invoke_flow",
    "to_schema",
    "render_template",
    "PowerAutomateInvocationResult",
]
