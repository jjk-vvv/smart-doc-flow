from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import Settings
from app.core.deps import get_settings
from app.services import frontend_static_service as service


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def frontend_root(request: Request, settings: Settings = Depends(get_settings)):
        if service.should_redirect_root_to_mobile(request, settings):
            return service.build_mobile_redirect_response(request)
        return service.serve_frontend_asset(settings, "")

    @router.get("/{full_path:path}")
    async def frontend_catch_all(request: Request, full_path: str, settings: Settings = Depends(get_settings)):
        if service.is_mobile_frontend_path(full_path):
            if service.should_redirect_mobile_path_to_desktop(request):
                return service.build_desktop_redirect_response(request, full_path)
            mobile_path = service.strip_mobile_frontend_prefix(full_path)
            return service.serve_frontend_app_asset(settings, mobile_path)

        first_segment = str(full_path or "").split("/", 1)[0].strip().lower()
        if first_segment in service.RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Reserved API namespace")
        return service.serve_frontend_asset(settings, full_path)

    return router


router = build_router()

__all__ = ["build_router", "router"]
