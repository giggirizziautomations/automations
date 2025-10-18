"""Logging utilities and middleware for structured output."""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Callable

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


_request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the request identifier for the current context."""

    return _request_id_ctx_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request identifier to each incoming request."""

    async def dispatch(self, request: Request, call_next: Callable[..., Any]):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = _request_id_ctx_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestIdFilter(logging.Filter):
    """Inject the request id in each log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = get_request_id() or "-"
        return True


def setup_logging() -> None:
    """Configure logging handlers and formatters."""

    settings = get_settings()
    logger = logging.getLogger()
    logger.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(request_id)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    logger.handlers = [handler]


def configure_app_logging(app: FastAPI) -> None:
    """Attach logging middleware and ensure handlers are configured."""

    setup_logging()
    app.add_middleware(RequestIDMiddleware)


__all__ = ["configure_app_logging", "get_request_id", "setup_logging", "RequestIDMiddleware"]
