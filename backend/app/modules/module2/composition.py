from __future__ import annotations

from fastapi import APIRouter

from app.modules.module2.api.router import router as module2_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(module2_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
