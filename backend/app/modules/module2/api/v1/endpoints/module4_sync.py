from __future__ import annotations

"""Compatibility endpoint module for legacy module4-sync import paths."""

try:
    from .sync import (
        GetOutboxRowFn,
        ListOutboxRowsFn,
        ListResponseFn,
        MetricsSnapshotFn,
        SerializeRowFn,
        build_router,
    )
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from app.modules.module2.api.v1.endpoints.sync import (
        GetOutboxRowFn,
        ListOutboxRowsFn,
        ListResponseFn,
        MetricsSnapshotFn,
        SerializeRowFn,
        build_router,
    )

__all__ = [
    "ListOutboxRowsFn",
    "GetOutboxRowFn",
    "ListResponseFn",
    "SerializeRowFn",
    "MetricsSnapshotFn",
    "build_router",
]

