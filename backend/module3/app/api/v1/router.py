from __future__ import annotations

from fastapi import APIRouter

from .endpoints.fusion import router as fusion_router


def build_api_v1_router() -> APIRouter:
    router = APIRouter()
    router.include_router(fusion_router)
    return router


__all__ = ["build_api_v1_router"]
