from fastapi import APIRouter

from .endpoints.graph import build_router as build_graph_endpoint_router
from ..deps import Module4RouterDeps


def build_api_v1_router(*, deps: Module4RouterDeps) -> APIRouter:
    router = APIRouter()
    router.include_router(build_graph_endpoint_router(deps=deps))
    return router
