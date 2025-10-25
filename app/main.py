"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_app_logging
from app.routers import auth
from app.routers import browser as browser_router
from app.routers import me as me_router
from app.routers import reports as reports_router
from app.routers import scraping as scraping_router
from app.routers import users as users_router


settings = get_settings()
app = FastAPI(title=settings.app_name)
configure_app_logging(app)

app.include_router(auth.password_router)
app.include_router(auth.client_router)
app.include_router(users_router.router)
app.include_router(me_router.router)
app.include_router(reports_router.router)
app.include_router(browser_router.router)
app.include_router(scraping_router.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""

    return {"status": "ok"}
