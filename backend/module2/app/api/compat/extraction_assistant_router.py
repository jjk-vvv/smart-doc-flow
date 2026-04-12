from __future__ import annotations

import warnings

from fastapi import APIRouter

try:
    from ..v1.endpoints.extraction_assistant import build_router as _build_api_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.v1.endpoints.extraction_assistant import build_router as _build_api_router


def build_extraction_assistant_router(*, assistant1_runtime) -> APIRouter:
    warnings.warn(
        "module2.app.routes.extraction_assistant_router is deprecated; "
        "use module2.app.api.v1.endpoints.extraction_assistant.build_router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router(assistant1_runtime=assistant1_runtime)


__all__ = [
    "build_extraction_assistant_router",
]
