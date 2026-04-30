from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_app_logging

from ..api.router import router as module3_router
from .bootstrap import ensure_module3_storage


def create_app() -> FastAPI:
    configure_app_logging()
    application = FastAPI(
        title="Module3 Fusion API",
        version="1.0.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ensure_module3_storage()
    application.include_router(module3_router)
    return application


app = create_app()


__all__ = ["app", "create_app"]
