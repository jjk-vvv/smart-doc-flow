from __future__ import annotations

import warnings

from fastapi import APIRouter

try:
    from ..v1.endpoints.sync import build_router as _build_api_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.v1.endpoints.sync import build_router as _build_api_router


def build_sync_router(
    *,
    list_outbox_rows,
    get_outbox_row,
    build_list_response,
    serialize_outbox_row,
    metrics_snapshot,
) -> APIRouter:
    warnings.warn(
        "module2.app.routes.sync_router is deprecated; "
        "use module2.app.api.v1.endpoints.sync.build_router instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_api_router(
        list_outbox_rows=list_outbox_rows,
        get_outbox_row=get_outbox_row,
        build_list_response=build_list_response,
        serialize_outbox_row=serialize_outbox_row,
        metrics_snapshot=metrics_snapshot,
    )


build_module4_sync_router = build_sync_router


__all__ = [
    "build_sync_router",
    "build_module4_sync_router",
]
