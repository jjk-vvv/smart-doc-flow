from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings
from app.core.deps import get_settings
from app.services import frontend_static_service as service


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def frontend_root(settings: Settings = Depends(get_settings)):
        return service.serve_frontend_asset(settings, "")

    @router.get("/{full_path:path}")
    async def frontend_catch_all(full_path: str, settings: Settings = Depends(get_settings)):
        first_segment = str(full_path or "").split("/", 1)[0].strip().lower()
        if first_segment in service.RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Reserved API namespace")
        return service.serve_frontend_asset(settings, full_path)

    return router


router = build_router()
