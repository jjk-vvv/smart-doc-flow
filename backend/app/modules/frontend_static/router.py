from __future__ import annotations

import warnings

from fastapi import APIRouter

from app.api.v1.endpoints.frontend_static import build_router as _build_api_router


def build_legacy_router() -> APIRouter:
    warnings.warn(
        "app.modules.frontend_static.router is deprecated; "
        "use app.api.v1.endpoints.frontend_static instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router()


router = _build_api_router()
