from __future__ import annotations

from fastapi import APIRouter

from app.modules.assistant.router import router as assistant_router
from app.modules.extraction.router import router as extraction_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(assistant_router)
    router.include_router(extraction_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
