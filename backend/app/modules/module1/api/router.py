from __future__ import annotations

from fastapi import APIRouter

from .endpoints.document import router as document_router
from .endpoints.health import router as health_router
from .endpoints.module1_placeholder import router as module1_placeholder_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(document_router)
    router.include_router(health_router)
    # Keep placeholder metadata endpoint during migration window.
    router.include_router(module1_placeholder_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
