from __future__ import annotations

"""Compatibility shim for office preview runtime.

The canonical implementation has moved to
``module2.app.services.preview.office`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports stable.
"""

try:
    from ..services.preview import office as _service_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.preview import office as _service_module  # type: ignore[import-not-found]


ConvertWordToPdfFn = _service_module.ConvertWordToPdfFn
SafeArtifactPathFn = _service_module.SafeArtifactPathFn
ArtifactFragmentFromPathFn = _service_module.ArtifactFragmentFromPathFn
ArtifactUrlFromFragmentFn = _service_module.ArtifactUrlFromFragmentFn
TimeoutSecFactory = _service_module.TimeoutSecFactory
TaskFactory = _service_module.TaskFactory
IsWordFileFn = _service_module.IsWordFileFn
OfficeConvertEnabledFn = _service_module.OfficeConvertEnabledFn
EnsureJobStartedFn = _service_module.EnsureJobStartedFn
SerializeJobFn = _service_module.SerializeJobFn
GetStatusPayloadFn = _service_module.GetStatusPayloadFn
OfficePreviewJob = _service_module.OfficePreviewJob
OfficePreviewService = _service_module.OfficePreviewService
OfficePreviewRequestService = _service_module.OfficePreviewRequestService
OfficePreviewRuntime = _service_module.OfficePreviewRuntime
OfficePreviewRequestRuntime = _service_module.OfficePreviewRequestRuntime


__all__ = [
    "ConvertWordToPdfFn",
    "SafeArtifactPathFn",
    "ArtifactFragmentFromPathFn",
    "ArtifactUrlFromFragmentFn",
    "TimeoutSecFactory",
    "TaskFactory",
    "IsWordFileFn",
    "OfficeConvertEnabledFn",
    "EnsureJobStartedFn",
    "SerializeJobFn",
    "GetStatusPayloadFn",
    "OfficePreviewJob",
    "OfficePreviewService",
    "OfficePreviewRequestService",
    "OfficePreviewRuntime",
    "OfficePreviewRequestRuntime",
]
