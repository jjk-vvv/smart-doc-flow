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
    from module2.app.api.v1.endpoints.sync import (  # type: ignore[import-not-found]
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
