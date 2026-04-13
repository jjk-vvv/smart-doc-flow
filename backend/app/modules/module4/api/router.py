from __future__ import annotations

from fastapi import APIRouter

from app.modules.gateway.router import router as gateway_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(gateway_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
