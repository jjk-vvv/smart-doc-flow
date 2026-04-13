from __future__ import annotations

from fastapi import APIRouter

from app.modules.module1_placeholder.router import router as placeholder_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(placeholder_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
