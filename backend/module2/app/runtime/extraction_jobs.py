from __future__ import annotations

"""Compatibility shim for extraction job runtime.

The canonical implementation has moved to
``module2.app.services.extraction.job`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.extraction import job as _service_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import job as _service_module  # type: ignore[import-not-found]


StateRootFactory = _service_module.StateRootFactory
SafeArtifactPathFn = _service_module.SafeArtifactPathFn
LoadedFileEntry = _service_module.LoadedFileEntry
JobStateFactory = _service_module.JobStateFactory
JobFileStateFactory = _service_module.JobFileStateFactory
DocumentValidateFn = _service_module.DocumentValidateFn
RunExtractionJobFn = _service_module.RunExtractionJobFn
TaskFactory = _service_module.TaskFactory
PersistSnapshotFn = _service_module.PersistSnapshotFn
TERMINAL_FILE_STATUSES = _service_module.TERMINAL_FILE_STATUSES
SKIPPABLE_FILE_STATUSES = _service_module.SKIPPABLE_FILE_STATUSES
ExtractionJobFileState = _service_module.ExtractionJobFileState
ExtractionJobState = _service_module.ExtractionJobState
ExtractionJobRuntime = _service_module.ExtractionJobRuntime


__all__ = [
    "StateRootFactory",
    "SafeArtifactPathFn",
    "LoadedFileEntry",
    "JobStateFactory",
    "JobFileStateFactory",
    "DocumentValidateFn",
    "RunExtractionJobFn",
    "TaskFactory",
    "PersistSnapshotFn",
    "TERMINAL_FILE_STATUSES",
    "SKIPPABLE_FILE_STATUSES",
    "ExtractionJobFileState",
    "ExtractionJobState",
    "ExtractionJobRuntime",
]
