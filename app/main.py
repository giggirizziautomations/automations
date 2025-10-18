"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_app_logging
from app.routers import auth as auth_router
from app.routers import me as me_router
from app.routers import reports as reports_router
from app.routers import users as users_router


settings = get_settings()
app = FastAPI(title=settings.app_name)
configure_app_logging(app)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(me_router.router)
app.include_router(reports_router.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""

    return {"status": "ok"}
