from __future__ import annotations

from fastapi import APIRouter

from app.modules.module1.api.router import router as module1_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(module1_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
