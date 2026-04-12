from __future__ import annotations

import warnings

from fastapi import APIRouter

try:
    from ..v1.endpoints.extraction_request import build_router as _build_api_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.v1.endpoints.extraction_request import build_router as _build_api_router


def build_extraction_request_router(*, extraction_request_runtime) -> APIRouter:
    warnings.warn(
        "module2.app.routes.extraction_request_router is deprecated; "
        "use module2.app.api.v1.endpoints.extraction_request.build_router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router(extraction_request_runtime=extraction_request_runtime)


__all__ = [
    "build_extraction_request_router",
]
