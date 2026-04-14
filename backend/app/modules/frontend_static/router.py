from __future__ import annotations

import warnings

from fastapi import APIRouter

from app.modules.frontend_static.api.router import build_router as _build_api_router


def build_legacy_router() -> APIRouter:
    warnings.warn(
        "app.modules.frontend_static.router is deprecated; "
        "use app.modules.frontend_static.api.router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router()


router = _build_api_router()
