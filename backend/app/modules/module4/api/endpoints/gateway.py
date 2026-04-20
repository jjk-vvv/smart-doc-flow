from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.deps import get_settings
from app.services import gateway_service as service

def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/gateway/info")
    async def gateway_info(settings: Settings = Depends(get_settings)):
        return service.build_gateway_info(settings)

    @router.get("/gateway/health")
    async def gateway_health(settings: Settings = Depends(get_settings)):
        payload = await service.build_gateway_health(settings)
        status_code = 200 if payload.get("ok") else 503
        return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))

    @router.get("/gateway/ready")
    async def gateway_ready(scope: str = "all", settings: Settings = Depends(get_settings)):
        payload, ready = await service.build_gateway_readiness(settings, scope)
        return JSONResponse(status_code=200 if ready else 503, content=jsonable_encoder(payload))

    return router


router = build_router()

__all__ = ["build_router", "router"]
