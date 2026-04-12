from __future__ import annotations

"""Compatibility shim for document tools runtime.

The canonical implementation has moved to
``module2.app.services.document.tools`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.document import tools as _service_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.document import tools as _service_module  # type: ignore[import-not-found]


SummarizeDocumentPayloadFn = _service_module.SummarizeDocumentPayloadFn
BuildDocumentTraceHitsFn = _service_module.BuildDocumentTraceHitsFn
FilterTraceHitsFn = _service_module.FilterTraceHitsFn
SummarizeResponseFactory = _service_module.SummarizeResponseFactory
TraceLocateResponseFactory = _service_module.TraceLocateResponseFactory
TraceDisplayKindFn = _service_module.TraceDisplayKindFn
DocumentToolsRuntime = _service_module.DocumentToolsRuntime
TraceSemanticsRuntime = _service_module.TraceSemanticsRuntime
TraceLocatorTextRuntime = _service_module.TraceLocatorTextRuntime
TraceLocatorPayloadRuntime = _service_module.TraceLocatorPayloadRuntime
PolymorphicLinksRuntime = _service_module.PolymorphicLinksRuntime
DocumentToolsSupportRuntime = _service_module.DocumentToolsSupportRuntime
FIELD_LABELS = _service_module.FIELD_LABELS
SUMMARY_NOTICE_SKIP = _service_module.SUMMARY_NOTICE_SKIP
SUMMARY_NOTICE_MAP = _service_module.SUMMARY_NOTICE_MAP


__all__ = [
    "SummarizeDocumentPayloadFn",
    "BuildDocumentTraceHitsFn",
    "FilterTraceHitsFn",
    "SummarizeResponseFactory",
    "TraceLocateResponseFactory",
    "TraceDisplayKindFn",
    "DocumentToolsRuntime",
    "TraceSemanticsRuntime",
    "TraceLocatorTextRuntime",
    "TraceLocatorPayloadRuntime",
    "PolymorphicLinksRuntime",
    "DocumentToolsSupportRuntime",
    "FIELD_LABELS",
    "SUMMARY_NOTICE_SKIP",
    "SUMMARY_NOTICE_MAP",
]
