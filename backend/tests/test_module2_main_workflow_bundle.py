from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_workflow_bundle_module = import_module("app.modules.module2.services.extraction.workflow_builder")


def test_build_module2_main_workflow_bundle_exposes_expected_runtime_fields() -> None:
    bundle = main_workflow_bundle_module.build_module2_main_workflow_bundle(
        build_stream_router=lambda: object(),
        cached_extraction_restore_runtime=object(),
        normalize_soft_warnings=lambda items: items,
        promote_visual_diagnostics=lambda diagnostics, **kwargs: diagnostics,
        persist_assistant_payload_artifact=lambda **kwargs: {"artifact_url": "", "artifact_path": ""},
        persist_field_results_artifact=lambda **kwargs: {"artifact_url": "", "artifact_path": ""},
        extraction_result_factory=lambda payload: payload,
        document_response_factory=lambda **kwargs: kwargs,
        save_extraction_result=lambda *args, **kwargs: None,
        document_input_plan_runtime=object(),
        word_input_preparation_runtime=object(),
        parse_preparation_runtime=object(),
        document_parse_recovery_runtime=object(),
        schema_session_runtime=object(),
        extraction_graph_runtime=object(),
        preflight_nonpdf_profile=lambda *args, **kwargs: {},
        resolve_nonpdf_budgets=lambda *args, **kwargs: {},
        resolve_nonpdf_plan=lambda *args, **kwargs: {},
        apply_field_extract_timeout_floor=lambda *args, **kwargs: 0.0,
        word_pdf_required=lambda: False,
        is_word_file=lambda file_name: False,
        office_convert_enabled=lambda: True,
        docx_native_recovery_enabled=lambda: True,
        validate_word_preconditions=lambda **kwargs: None,
        resolve_conversion_timeout=lambda **kwargs: 30.0,
        build_word_pdf_success=lambda **kwargs: {},
        resolve_word_pdf_failure=lambda **kwargs: {},
        build_doc_to_docx_success=lambda **kwargs: {},
        build_doc_to_docx_failure=lambda **kwargs: {},
        word_pdf_semaphore=asyncio.Semaphore(1),
        ensure_preview_job_started=lambda **kwargs: None,
        await_or_reuse_pdf=lambda **kwargs: {},
        run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
        convert_doc_to_docx_with_timeout=lambda **kwargs: b"",
        tighten_parse_budgets_before_parse=lambda **kwargs: {},
        build_parse_session=lambda **kwargs: {},
        build_parse_attempt_runner=lambda **kwargs: object(),
        acquire_parse_execution_slots=lambda *args, **kwargs: None,
        run_parse_in_process_pool=lambda **kwargs: {},
        resolve_parse_progress_ramp_sec=lambda **kwargs: 12.0,
        unpack_parse_output=lambda output: output,
        visual_parse_policy_runtime=object(),
        parse_fallback_coordinator_runtime=object(),
        docx_native_recovery_runtime=object(),
        fasttrack_fallback_runtime=object(),
        visual_chain_required=lambda: False,
        visual_strict_mode=lambda: False,
        disable_fasttrack_fallback=lambda: False,
        build_visual_chain_contract=lambda **kwargs: {"required": False, "satisfied": True},
        extraction_llm_semaphore=asyncio.Semaphore(1),
        detect_domain_template=lambda **kwargs: "general",
        extract_text_for_schema=lambda **kwargs: "",
        resolve_effective_schema=lambda **kwargs: {},
        resolve_dynamic_extract_timeout_sec=lambda **kwargs: {"timeout_sec": 30.0},
        run_graph=lambda **kwargs: {},
        resolve_extract_progress_ramp_sec=lambda **kwargs: 20.0,
        quick_extract_from_tables=lambda **kwargs: {},
        disable_quick_table_fallback=lambda: False,
        xlsx_workbook_artifact_runtime=object(),
        logger=object(),
        post_parse_quality_runtime=object(),
        post_parse_artifact_runtime=object(),
        diagnostics_builder_runtime=object(),
        extraction_response_runtime=object(),
        graph_diagnostics_factory=lambda: {},
        current_extraction_logic_version=lambda: "v1",
        current_extraction_logic_components=lambda: {"version": "v1"},
        field_naming_version="field-v1",
        schema_rule_versions={"schema": "v1"},
        is_low_value_auto_schema_field_name=lambda name: False,
        has_meaningful_value=lambda value: True,
        is_low_value_quick_fallback_value=lambda value: False,
        is_recoverable_timeout_error=lambda error: False,
        filter_low_value_auto_results=lambda **kwargs: {},
        effective_quality_schema_fields=lambda **kwargs: {},
        result_quality_snapshot=lambda **kwargs: {},
        strip_recovered_extract_warnings=lambda warnings: warnings,
        write_artifact_bytes=lambda **kwargs: ("artifact/path", "/artifacts/x"),
        crop_pdf_region_png=lambda **kwargs: b"",
        build_document_trace_hits=lambda **kwargs: [],
        trace_stats_builder=lambda **kwargs: {},
        build_polymorphic_links=lambda **kwargs: [],
        count_table_cells=lambda tables: 0,
        table_quality_avg=lambda tables: 0.0,
        table_source_counts=lambda tables: {},
        count_figure_dataframe_cells=lambda figures: 0,
        figure_pages=lambda figures: [],
        figure_source_counts=lambda figures: {},
        persist_assistant1_source_markdown_artifact=lambda **kwargs: {"artifact_url": "", "artifact_path": ""},
    )

    assert bundle.document_execution_runtime is not None
    assert bundle.document_pipeline_runtime is not None
    assert bundle.document_postprocess_runtime is not None
    assert bundle.document_workflow_runtime is not None
