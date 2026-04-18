from __future__ import annotations

from fastapi import APIRouter

from .endpoints import bootstrap_router, catalog_router, chat_router, diagnostics_router, health_router


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/platform-assistant", tags=["platform-assistant"])
    router.include_router(health_router)
    router.include_router(diagnostics_router)
    router.include_router(catalog_router)
    router.include_router(bootstrap_router)
    router.include_router(chat_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
