from __future__ import annotations

from fastapi import APIRouter

from .endpoints.frontend_static import router as frontend_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(frontend_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
