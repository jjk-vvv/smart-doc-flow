from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "removed_module_path",
    [
        "app.modules.module2.runtime.main_foundation_bundle",
        "app.modules.module2.runtime.main_entry_bundle",
        "app.modules.module2.runtime.main_extraction_bundle",
        "app.modules.module2.runtime.main_document_io_bundle",
        "app.modules.module2.runtime.main_geometry_bundle",
        "app.modules.module2.runtime.main_nonpdf_bundle",
        "app.modules.module2.runtime.main_platform_bundle",
        "app.modules.module2.runtime.main_policy_bundle",
        "app.modules.module2.runtime.main_progress_bundle",
        "app.modules.module2.runtime.main_quality_bundle",
        "app.modules.module2.runtime.main_quick_extract_bundle",
        "app.modules.module2.runtime.main_result_filter_bundle",
        "app.modules.module2.runtime.main_schema_context_bundle",
        "app.modules.module2.runtime.main_schema_fields_bundle",
        "app.modules.module2.runtime.main_schema_inference_bundle",
        "app.modules.module2.runtime.main_schema_llm_bundle",
        "app.modules.module2.runtime.main_schema_pipeline_bundle",
        "app.modules.module2.runtime.main_schema_primitives_bundle",
        "app.modules.module2.runtime.main_schema_resolution_bundle",
        "app.modules.module2.runtime.main_schema_selection_bundle",
        "app.modules.module2.runtime.main_schema_semantics_bundle",
        "app.modules.module2.runtime.main_service_bundle",
        "app.modules.module2.runtime.main_support_bundle",
        "app.modules.module2.runtime.main_workflow_bundle",
        "app.modules.module2.runtime.document_trace_runtime",
        "app.modules.module2.runtime.extraction_jobs",
        "app.modules.module2.runtime.extraction_requests",
        "app.modules.module2.runtime.extraction_executor",
        "app.modules.module2.runtime.office_preview",
        "app.modules.module2.runtime.module4_sync_callback_bundle",
    ],
)
def test_round8_removed_module2_runtime_compat_shims_raise_not_found(removed_module_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_module_path)

