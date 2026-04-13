from __future__ import annotations

from fastapi import APIRouter

from .....routes.fusion_routes import router as legacy_fusion_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(legacy_fusion_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
