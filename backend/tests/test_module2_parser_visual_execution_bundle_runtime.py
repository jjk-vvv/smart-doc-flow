from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_execution_bundle_runtime_module = import_module("module2.app.core.parsers.parser_visual_execution_bootstrap_runtime")

ParserVisualExecutionBundleRuntime = parser_visual_execution_bundle_runtime_module.ParserVisualExecutionBundleRuntime


def test_parser_visual_execution_bundle_runtime_builds_planner_and_materializer_kwargs() -> None:
    runtime = ParserVisualExecutionBundleRuntime()

    build_visual_object_context = lambda **kwargs: {"page": kwargs.get("page_no", 0)}
    get_cropper = lambda: "cropper"
    build_table_from_visual_payload = lambda **kwargs: ({"table_id": "t1"}, kwargs.get("emitted_cells", 0))
    table_payload_has_content = lambda payload: True
    build_figure_from_visual_payload = lambda **kwargs: {"figure_id": "f1"}
    figure_payload_has_content = lambda payload: True

    planner_kwargs = runtime.build_visual_job_planner_kwargs(
        build_visual_object_context=build_visual_object_context,
        get_cropper=get_cropper,
    )
    materializer_kwargs = runtime.build_visual_result_materializer_kwargs(
        table_cell_cap=3000,
        build_table_from_visual_payload=build_table_from_visual_payload,
        table_payload_has_content=table_payload_has_content,
        build_figure_from_visual_payload=build_figure_from_visual_payload,
        figure_payload_has_content=figure_payload_has_content,
    )

    assert planner_kwargs["build_visual_object_context"](page_no=3) == {"page": 3}
    assert planner_kwargs["get_cropper"]() == "cropper"
    assert materializer_kwargs["table_cell_cap"] == 3000
    assert materializer_kwargs["build_table_from_visual_payload"](emitted_cells=12) == (
        {"table_id": "t1"},
        12,
    )
    assert materializer_kwargs["table_payload_has_content"]({}) is True
    assert materializer_kwargs["build_figure_from_visual_payload"]() == {"figure_id": "f1"}
    assert materializer_kwargs["figure_payload_has_content"]({}) is True


def test_parser_visual_execution_bundle_runtime_builds_execution_and_finalizer_kwargs() -> None:
    runtime = ParserVisualExecutionBundleRuntime()

    plan_visual_vision_jobs = lambda **kwargs: {"vision_jobs": []}
    run_visual_vision_jobs = lambda **kwargs: {0: {"payload": {}}}
    materialize_visual_results = lambda **kwargs: {"table_blocks": [], "figure_blocks": []}
    build_visual_parse_status_fields = lambda **kwargs: {"chain_status": "success", **kwargs}
    merge_same_page_tables = lambda tables: tables
    merge_cross_page_tables = lambda tables: tables
    prune_fragment_tables = lambda tables: tables
    merge_figure_blocks = lambda current, extra: current + extra

    execution_kwargs = runtime.build_visual_execution_kwargs(
        default_table_max_per_page=4,
        default_figure_max_per_page=3,
        default_figure_refine_budget=5,
        default_figure_refine_min_score=6,
        plan_visual_vision_jobs=plan_visual_vision_jobs,
        run_visual_vision_jobs=run_visual_vision_jobs,
        materialize_visual_results=materialize_visual_results,
        extract_native_tables_with_fitz=lambda **kwargs: [{"table_id": "pdf_fitz_t1"}],
    )
    finalizer_kwargs = runtime.build_visual_parse_finalizer_kwargs(
        table_merge_enable=True,
        visual_vision_concurrency=8,
        default_figure_refine_budget=5,
        build_visual_parse_status_fields=build_visual_parse_status_fields,
        merge_same_page_tables=merge_same_page_tables,
        merge_cross_page_tables=merge_cross_page_tables,
        prune_fragment_tables=prune_fragment_tables,
        merge_figure_blocks=merge_figure_blocks,
    )

    assert execution_kwargs["default_table_max_per_page"] == 4
    assert execution_kwargs["default_figure_max_per_page"] == 3
    assert execution_kwargs["default_figure_refine_budget"] == 5
    assert execution_kwargs["default_figure_refine_min_score"] == 6
    assert execution_kwargs["plan_visual_vision_jobs"]() == {"vision_jobs": []}
    assert execution_kwargs["run_visual_vision_jobs"]() == {0: {"payload": {}}}
    assert execution_kwargs["materialize_visual_results"]() == {"table_blocks": [], "figure_blocks": []}
    assert execution_kwargs["extract_native_tables_with_fitz"]() == [{"table_id": "pdf_fitz_t1"}]
    assert finalizer_kwargs["table_merge_enable"] is True
    assert finalizer_kwargs["visual_vision_concurrency"] == 8
    assert finalizer_kwargs["default_figure_refine_budget"] == 5
    assert finalizer_kwargs["build_visual_parse_status_fields"](visual_mode="visual_blocks")["visual_mode"] == "visual_blocks"
    assert finalizer_kwargs["merge_same_page_tables"]([{"table_id": "t1"}]) == [{"table_id": "t1"}]
    assert finalizer_kwargs["merge_cross_page_tables"]([{"table_id": "t2"}]) == [{"table_id": "t2"}]
    assert finalizer_kwargs["prune_fragment_tables"]([{"table_id": "t3"}]) == [{"table_id": "t3"}]
    assert finalizer_kwargs["merge_figure_blocks"]([{"figure_id": "f1"}], [{"figure_id": "f2"}]) == [
        {"figure_id": "f1"},
        {"figure_id": "f2"},
    ]


def test_parser_visual_execution_bundle_runtime_builds_text_orchestrator_and_entrypoint_kwargs() -> None:
    runtime = ParserVisualExecutionBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)
    split_page_text = lambda text: [text] if text else []
    build_visual_parse_status_fields = lambda **kwargs: {"artifact_status": "artifact_sparse", **kwargs}
    build_text_only_result = lambda **kwargs: ("markdown", {}, [], {})
    finalize_no_blocks = lambda **kwargs: {"stats": {"visual_failure": "no_visual_blocks"}}
    finalize_success = lambda **kwargs: {"stats": {"visual_table_count": 1}}
    bootstrap = lambda **kwargs: {"native_page_count": 3}
    prepare_context = lambda **kwargs: {"page_lines": {1: ["line"]}}
    build_initial_refs = lambda **kwargs: {"parts": [], "bbox_map": {}, "page_dims": {}}
    prioritize_layout_objects = lambda *args, **kwargs: ([], {})
    execute_visual = lambda **kwargs: {"table_blocks": [], "figure_blocks": []}
    resolve_no_layout_objects = lambda **kwargs: {"result": None}
    resolve_no_selected_objects = lambda **kwargs: {"result": None}
    finalize_parse = lambda **kwargs: {"result": None}
    parse_pdf_visual_first = lambda **kwargs: {"outcome": {"result": None}}
    visual_backend_available = lambda: (True, "")
    parse_pdf_native = lambda **kwargs: {"markdown": "native"}
    get_last_mineru_run_meta = lambda: {"status": "ok"}

    text_only_kwargs = runtime.build_visual_text_only_builder_kwargs(
        visual_text_only_min_chars=120,
        normalize_text=normalize_text,
        append_ref=append_ref,
        split_page_text=split_page_text,
        build_visual_parse_status_fields=build_visual_parse_status_fields,
    )
    orchestrator_kwargs = runtime.build_visual_parse_orchestrator_kwargs(
        build_text_only_result=build_text_only_result,
        finalize_no_blocks=finalize_no_blocks,
        finalize_success=finalize_success,
    )
    pdf_visual_parse_kwargs = runtime.build_pdf_visual_parse_kwargs(
        bootstrap=bootstrap,
        prepare_context=prepare_context,
        build_initial_refs=build_initial_refs,
        prioritize_layout_objects=prioritize_layout_objects,
        execute_visual=execute_visual,
        resolve_no_layout_objects=resolve_no_layout_objects,
        resolve_no_selected_objects=resolve_no_selected_objects,
        finalize_parse=finalize_parse,
    )
    pdf_parse_kwargs = runtime.build_pdf_parse_kwargs(
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=False,
        parse_pdf_visual_first=parse_pdf_visual_first,
        visual_backend_available=visual_backend_available,
        parse_pdf_native=parse_pdf_native,
        get_last_mineru_run_meta=get_last_mineru_run_meta,
    )
    visual_vision_jobs_kwargs = runtime.build_visual_vision_jobs_kwargs(
        visual_vision_concurrency=6,
    )

    assert text_only_kwargs["visual_text_only_min_chars"] == 120
    assert text_only_kwargs["normalize_text"]("  txt  ") == "txt"
    assert text_only_kwargs["split_page_text"]("page text") == ["page text"]
    assert text_only_kwargs["build_visual_parse_status_fields"](visual_mode="text_only")["visual_mode"] == "text_only"
    assert orchestrator_kwargs["build_text_only_result"]() == ("markdown", {}, [], {})
    assert orchestrator_kwargs["finalize_no_blocks"]() == {"stats": {"visual_failure": "no_visual_blocks"}}
    assert orchestrator_kwargs["finalize_success"]() == {"stats": {"visual_table_count": 1}}
    assert pdf_visual_parse_kwargs["bootstrap"]() == {"native_page_count": 3}
    assert pdf_visual_parse_kwargs["prepare_context"]() == {"page_lines": {1: ["line"]}}
    assert pdf_visual_parse_kwargs["build_initial_refs"]() == {"parts": [], "bbox_map": {}, "page_dims": {}}
    assert pdf_visual_parse_kwargs["prioritize_layout_objects"]() == ([], {})
    assert pdf_visual_parse_kwargs["execute_visual"]() == {"table_blocks": [], "figure_blocks": []}
    assert pdf_visual_parse_kwargs["resolve_no_layout_objects"]() == {"result": None}
    assert pdf_visual_parse_kwargs["resolve_no_selected_objects"]() == {"result": None}
    assert pdf_visual_parse_kwargs["finalize_parse"]() == {"result": None}
    assert pdf_parse_kwargs["enable_mineru_layout"] is True
    assert pdf_parse_kwargs["pipeline_mode"] == "visual_first"
    assert pdf_parse_kwargs["visual_first_allow_legacy_fallback"] is False
    assert pdf_parse_kwargs["parse_pdf_visual_first"]() == {"outcome": {"result": None}}
    assert pdf_parse_kwargs["visual_backend_available"]() == (True, "")
    assert pdf_parse_kwargs["parse_pdf_native"]() == {"markdown": "native"}
    assert pdf_parse_kwargs["get_last_mineru_run_meta"]() == {"status": "ok"}
    assert visual_vision_jobs_kwargs["visual_vision_concurrency"] == 6
