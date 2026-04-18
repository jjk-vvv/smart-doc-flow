from __future__ import annotations

from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import get_settings
from app.core.env import load_managed_env_files
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan_context
from app.core.logging import configure_app_logging
from app.core.middleware import register_middleware


def create_app() -> FastAPI:
    """Build the unified FastAPI application instance."""

    load_managed_env_files(scopes=("module1", "module2", "module3", "module4", "backend"))
    settings = get_settings()
    configure_app_logging()

    app = FastAPI(
        title="Smart Doc Flow Unified Gateway",
        version="0.1.0",
        lifespan=lifespan_context,
    )
    register_middleware(app, settings)
    register_exception_handlers(app)
    app.include_router(build_api_router(settings=settings))
    return app


__all__ = ["create_app"]
