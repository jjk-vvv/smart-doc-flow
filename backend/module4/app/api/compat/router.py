from __future__ import annotations

import warnings

from fastapi import APIRouter

from ..deps import Module4RouterDeps
from ..v1.endpoints import module4 as _module4_endpoint
from ..v1.endpoints.module4 import (
    build_router as _build_api_router,
    graphrag_query_response_service,
)

__all__ = [
    "Module4RouterDeps",
    "build_module4_router",
    "graphrag_query_response_service",
]


def build_module4_router(*, deps: Module4RouterDeps) -> APIRouter:
    # Keep monkeypatch-based compatibility for legacy tests/tools that still patch
    # `module4.app.router.graphrag_query_response_service`.
    _module4_endpoint.graphrag_query_response_service = graphrag_query_response_service
    warnings.warn(
        "module4.app.router.build_module4_router is deprecated; "
        "use module4.app.api.v1.endpoints.module4.build_router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router(deps=deps)

