from fastapi import APIRouter

from app.core.config import Settings, get_settings
from app.modules.registry import resolve_module_routers


def build_api_v1_router(*, settings: Settings | None = None) -> APIRouter:
    router = APIRouter()
    resolved_settings = settings or get_settings()
    for _, module_router in resolve_module_routers(resolved_settings):
        router.include_router(module_router)
    return router
