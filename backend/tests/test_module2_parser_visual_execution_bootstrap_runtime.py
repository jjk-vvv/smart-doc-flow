from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_execution_bootstrap_module = import_module("module2.app.core.parsers.parser_visual_execution_bootstrap_runtime")
parser_visual_execution_bundle_module = parser_visual_execution_bootstrap_module

ParserVisualExecutionBootstrapRuntime = (
    parser_visual_execution_bootstrap_module.ParserVisualExecutionBootstrapRuntime
)
ParserVisualExecutionBundleRuntime = parser_visual_execution_bundle_module.ParserVisualExecutionBundleRuntime


def test_parser_visual_execution_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserVisualExecutionBootstrapRuntime()

    attrs = runtime.build_visual_execution_runtime_attrs(
        parser_visual_execution_bundle_runtime=ParserVisualExecutionBundleRuntime(),
        table_cell_cap=2000,
        visual_table_max_per_page=3,
        visual_figure_max_per_page=4,
        visual_figure_refine_budget=2,
        visual_figure_refine_min_score=5,
        visual_vision_concurrency=2,
        visual_text_only_min_chars=80,
        table_merge_enable=True,
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=True,
        build_visual_object_context=lambda **kwargs: {"page": kwargs.get("page_no", 0)},
        get_cropper=lambda: object(),
        build_table_from_visual_payload=lambda **kwargs: (None, kwargs["emitted_cells"]),
        table_payload_has_content=lambda payload: bool(payload),
        build_figure_from_visual_payload=lambda **kwargs: None,
        figure_payload_has_content=lambda payload: bool(payload),
        build_visual_parse_status_fields=lambda **kwargs: {"status": "ok"},
        merge_same_page_tables=lambda table_blocks: list(table_blocks or []),
        merge_cross_page_tables=lambda table_blocks: list(table_blocks or []),
        prune_fragment_tables=lambda table_blocks: list(table_blocks or []),
        merge_figure_blocks=lambda left, right: list(left or []) + list(right or []),
        normalize_text=lambda text: str(text).strip(),
        split_page_text=lambda text: [str(text).strip()] if str(text).strip() else [],
        bootstrap=lambda **kwargs: {},
        prepare_context=lambda **kwargs: {},
        build_initial_refs=lambda **kwargs: {},
        prioritize_layout_objects=lambda *args, **kwargs: ([], {}),
        extract_native_tables_with_fitz=lambda **kwargs: [{"table_id": "pdf_fitz_t1"}],
        parse_pdf_visual_first=lambda **kwargs: None,
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: {},
        get_last_mineru_run_meta=lambda: {"status": "ok"},
    )

    expected_keys = {
        "_visual_vision_jobs_runtime",
        "_visual_job_planner_runtime",
        "_visual_result_materializer_runtime",
        "_visual_execution_runtime",
        "_visual_parse_finalizer_runtime",
        "_visual_text_only_builder_runtime",
        "_visual_parse_orchestrator_runtime",
        "_pdf_visual_parse_runtime",
        "_pdf_parse_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_visual_vision_jobs_runtime"], "run_jobs")
    assert hasattr(attrs["_visual_job_planner_runtime"], "plan_jobs")
    assert hasattr(attrs["_visual_result_materializer_runtime"], "materialize")
    assert hasattr(attrs["_visual_execution_runtime"], "execute")
    assert hasattr(attrs["_visual_parse_finalizer_runtime"], "finalize_success")
    assert hasattr(attrs["_visual_text_only_builder_runtime"], "build_result")
    assert hasattr(attrs["_visual_parse_orchestrator_runtime"], "finalize_parse")
    assert hasattr(attrs["_pdf_visual_parse_runtime"], "parse_pdf_visual_first")
    assert hasattr(attrs["_pdf_parse_runtime"], "parse_pdf")
    assert attrs["_visual_execution_runtime"]._run_visual_vision_jobs.__self__ is attrs["_visual_vision_jobs_runtime"]
    assert attrs["_visual_execution_runtime"]._materialize_visual_results.__self__ is attrs["_visual_result_materializer_runtime"]
    assert attrs["_visual_execution_runtime"]._extract_native_tables_with_fitz() == [{"table_id": "pdf_fitz_t1"}]
    assert attrs["_pdf_visual_parse_runtime"]._execute_visual.__self__ is attrs["_visual_execution_runtime"]
