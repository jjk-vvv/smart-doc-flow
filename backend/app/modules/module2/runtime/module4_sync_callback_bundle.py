from __future__ import annotations

"""Compatibility shim for legacy module4 sync callback bundle imports."""

from .sync_callback_bundle import (
    DocumentSyncMode,
    EnqueueDocumentSyncFn,
    EnqueueDocumentSyncForSeedFn,
    GetOutboxRowFn,
    ListOutboxRowsFn,
    ListResponseFn,
    MetricsSnapshotFn,
    Module4SyncCallbackBundle,
    ScheduleOutboxFn,
    SerializeOutboxRowFn,
    SourceBatchKeyFn,
    build_module4_sync_callback_bundle,
)

__all__ = [
    "ScheduleOutboxFn",
    "EnqueueDocumentSyncFn",
    "EnqueueDocumentSyncForSeedFn",
    "ListOutboxRowsFn",
    "GetOutboxRowFn",
    "ListResponseFn",
    "SerializeOutboxRowFn",
    "MetricsSnapshotFn",
    "SourceBatchKeyFn",
    "DocumentSyncMode",
    "Module4SyncCallbackBundle",
    "build_module4_sync_callback_bundle",
]
