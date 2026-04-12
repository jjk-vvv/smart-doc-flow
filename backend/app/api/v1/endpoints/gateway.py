from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings
from app.core.deps import get_settings
from app.services import gateway_service as service

ALL_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/gateway/info")
    async def gateway_info(settings: Settings = Depends(get_settings)):
        return service.build_gateway_info(settings)

    @router.get("/gateway/health")
    async def gateway_health(settings: Settings = Depends(get_settings)):
        payload = await service.build_gateway_health(settings)
        status_code = 200 if payload.get("ok") else 503
        return JSONResponse(status_code=status_code, content=payload)

    @router.get("/gateway/ready")
    async def gateway_ready(scope: str = "all", settings: Settings = Depends(get_settings)):
        payload, ready = await service.build_gateway_readiness(settings, scope)
        return JSONResponse(status_code=200 if ready else 503, content=payload)

    @router.api_route("/module4", methods=ALL_PROXY_METHODS)
    @router.api_route("/module4/{path:path}", methods=ALL_PROXY_METHODS)
    async def proxy_module4(
        path: str = "",
        request: Request = None,
        settings: Settings = Depends(get_settings),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        upstream_path = "/module4" if not path else f"/module4/{path}"
        return await service.proxy_module4_request(
            request,
            settings,
            upstream_path,
            additional_headers=current_user.to_forward_headers(),
        )

    return router


router = build_router()
