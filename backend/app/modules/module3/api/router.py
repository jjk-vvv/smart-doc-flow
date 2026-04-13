from __future__ import annotations

from fastapi import APIRouter

from module3.app.api.v1.router import build_api_v1_router


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(build_api_v1_router())
    return router


router = build_router()

__all__ = ["build_router", "router"]
