from __future__ import annotations

import warnings

from fastapi import APIRouter

try:
    from ..v1.endpoints.extraction_support import build_router as _build_api_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.v1.endpoints.extraction_support import build_router as _build_api_router


def build_extraction_support_router(
    *,
    office_preview_request_runtime,
    document_tools_runtime,
    clear_cache_request,
    serve_layout_preview,
    serve_artifact,
    build_health_payload,
) -> APIRouter:
    warnings.warn(
        "module2.app.routes.extraction_support_router is deprecated; "
        "use module2.app.api.v1.endpoints.extraction_support.build_router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router(
        office_preview_request_runtime=office_preview_request_runtime,
        document_tools_runtime=document_tools_runtime,
        clear_cache_request=clear_cache_request,
        serve_layout_preview=serve_layout_preview,
        serve_artifact=serve_artifact,
        build_health_payload=build_health_payload,
    )


__all__ = [
    "build_extraction_support_router",
]
