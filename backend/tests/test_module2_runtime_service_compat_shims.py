from __future__ import annotations

from importlib import import_module


def test_module2_document_tools_runtime_shim_exports_service_symbols() -> None:
    compat_module = import_module("module2.app.runtime.document_trace_runtime")
    service_module = import_module("module2.app.services.document_tools_service")

    assert compat_module.DocumentToolsRuntime is service_module.DocumentToolsRuntime
    assert compat_module.TraceSemanticsRuntime is service_module.TraceSemanticsRuntime
    assert compat_module.TraceLocatorTextRuntime is service_module.TraceLocatorTextRuntime
    assert compat_module.TraceLocatorPayloadRuntime is service_module.TraceLocatorPayloadRuntime
    assert compat_module.DocumentToolsSupportRuntime is service_module.DocumentToolsSupportRuntime


def test_module2_extraction_job_runtime_shim_exports_service_symbols() -> None:
    compat_module = import_module("module2.app.runtime.extraction_jobs")
    service_module = import_module("module2.app.services.extraction_job_service")

    assert compat_module.ExtractionJobFileState is service_module.ExtractionJobFileState
    assert compat_module.ExtractionJobState is service_module.ExtractionJobState
    assert compat_module.ExtractionJobRuntime is service_module.ExtractionJobRuntime
