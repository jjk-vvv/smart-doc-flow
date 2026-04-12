from __future__ import annotations

"""Compatibility shim for extraction job execution runtime.

The canonical implementation has moved to
``module2.app.services.extraction.executor`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports stable.
"""

try:
    from ..services.extraction import executor as _service_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import executor as _service_module  # type: ignore[import-not-found]


ProcessSingleDocBytesFn = _service_module.ProcessSingleDocBytesFn
ExtractionJobExecutionService = _service_module.ExtractionJobExecutionService
ExtractionJobExecutor = _service_module.ExtractionJobExecutor


__all__ = [
    "ProcessSingleDocBytesFn",
    "ExtractionJobExecutionService",
    "ExtractionJobExecutor",
]
