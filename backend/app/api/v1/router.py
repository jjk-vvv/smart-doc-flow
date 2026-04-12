from fastapi import APIRouter

from app.api.v1.endpoints.assistant import router as assistant_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.extraction import router as extraction_router
from app.api.v1.endpoints.frontend_static import router as frontend_static_router
from app.api.v1.endpoints.gateway import router as gateway_router
from app.api.v1.endpoints.module1_placeholder import router as module1_placeholder_router


def build_api_v1_router() -> APIRouter:
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(assistant_router)
    router.include_router(extraction_router)
    router.include_router(gateway_router)
    router.include_router(module1_placeholder_router)
    router.include_router(frontend_static_router)
    return router

