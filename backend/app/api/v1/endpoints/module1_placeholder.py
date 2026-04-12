from __future__ import annotations

from fastapi import APIRouter

from app.services.module1_placeholder_service import build_placeholder_info


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/module1-placeholder/info")
    async def module1_placeholder_info():
        return build_placeholder_info()

    return router


router = build_router()
