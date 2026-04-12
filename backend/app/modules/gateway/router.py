from __future__ import annotations

import warnings

from fastapi import APIRouter

from app.api.v1.endpoints.gateway import build_router as _build_api_router


def build_legacy_router() -> APIRouter:
    warnings.warn(
        "app.modules.gateway.router is deprecated; "
        "use app.api.v1.endpoints.gateway instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router()


router = _build_api_router()
