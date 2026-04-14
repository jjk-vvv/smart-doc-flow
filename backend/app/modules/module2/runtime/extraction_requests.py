from __future__ import annotations

"""Compatibility shim for extraction request runtime.

The canonical implementation has moved to
``module2.app.services.extraction.request`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports stable.
"""

try:
    from ..services.extraction import request as _service_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.extraction import request as _service_module  # type: ignore[import-not-found]


LoadedFileEntry = _service_module.LoadedFileEntry
ProcessSingleDocBytesFn = _service_module.ProcessSingleDocBytesFn
ParseSchemaFormFn = _service_module.ParseSchemaFormFn
WriteArtifactBytesFn = _service_module.WriteArtifactBytesFn
SchemaHashFn = _service_module.SchemaHashFn
BuildStreamRouterFn = _service_module.BuildStreamRouterFn
EnsureProviderReadyFn = _service_module.EnsureProviderReadyFn
Module4TenantFn = _service_module.Module4TenantFn
ExtractionResultFactory = _service_module.ExtractionResultFactory
DocumentResponseFactory = _service_module.DocumentResponseFactory
BatchResponseFactory = _service_module.BatchResponseFactory
ExtractionRequestService = _service_module.ExtractionRequestService
ExtractionRequestRuntime = _service_module.ExtractionRequestRuntime


__all__ = [
    "LoadedFileEntry",
    "ProcessSingleDocBytesFn",
    "ParseSchemaFormFn",
    "WriteArtifactBytesFn",
    "SchemaHashFn",
    "BuildStreamRouterFn",
    "EnsureProviderReadyFn",
    "Module4TenantFn",
    "ExtractionResultFactory",
    "DocumentResponseFactory",
    "BatchResponseFactory",
    "ExtractionRequestService",
    "ExtractionRequestRuntime",
]

