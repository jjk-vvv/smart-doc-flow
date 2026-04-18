from __future__ import annotations

from importlib import import_module
import pytest


def test_module2_canonical_runtime_services_are_importable() -> None:
    document_tools_module = import_module("app.modules.module2.services.document.tools")
    extraction_job_module = import_module("app.modules.module2.services.extraction.job")
    extraction_request_module = import_module("app.modules.module2.services.extraction.request")
    extraction_executor_module = import_module("app.modules.module2.services.extraction.executor")
    office_preview_module = import_module("app.modules.module2.services.preview.office")

    assert callable(document_tools_module.DocumentToolsRuntime)
    assert callable(extraction_job_module.ExtractionJobRuntime)
    assert callable(extraction_request_module.ExtractionRequestService)
    assert callable(extraction_executor_module.ExtractionJobExecutionService)
    assert callable(office_preview_module.OfficePreviewRuntime)
    assert not hasattr(extraction_request_module, "ExtractionRequestRuntime")
    assert not hasattr(extraction_executor_module, "ExtractionJobExecutor")


@pytest.mark.parametrize(
    "removed_module_path",
    [
        "app.modules.module2.runtime.document_trace_runtime",
        "app.modules.module2.runtime.extraction_jobs",
        "app.modules.module2.runtime.extraction_requests",
        "app.modules.module2.runtime.extraction_executor",
        "app.modules.module2.runtime.office_preview",
        "app.modules.module2.runtime.module4_sync_callback_bundle",
        "app.modules.module2.services.document_tools_service",
        "app.modules.module2.services.extraction_job_service",
        "app.modules.module2.services.extraction_executor_service",
        "app.modules.module2.services.extraction_request_service",
        "app.modules.module2.services.office_preview_service",
    ],
)
def test_module2_removed_runtime_and_service_compat_shims_raise_not_found(removed_module_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_module_path)
