from __future__ import annotations

from fastapi import APIRouter, Depends

from .endpoints import (
    health_router,
    modification_router,
    preview_router,
    save_router,
    stream_router,
)
from .deps import require_module1_authenticated_user


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)

    protected_router = APIRouter(dependencies=[Depends(require_module1_authenticated_user)])
    protected_router.include_router(modification_router)
    protected_router.include_router(preview_router)
    protected_router.include_router(save_router)
    protected_router.include_router(stream_router)

    router.include_router(protected_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
