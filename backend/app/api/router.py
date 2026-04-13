from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.router import build_api_v1_router
from app.core.config import Settings, get_settings


def build_api_router(*, settings: Settings | None = None) -> APIRouter:
    router = APIRouter()
    resolved_settings = settings or get_settings()
    router.include_router(build_api_v1_router(settings=resolved_settings))
    return router


__all__ = ["build_api_router"]
