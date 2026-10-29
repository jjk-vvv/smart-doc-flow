from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


visual_parse_orchestrator_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_parse_orchestrator.py"],
    "_smart_doc_flow_module2_visual_parse_orchestrator",
)

VisualParseOrchestratorRuntime = visual_parse_orchestrator_module.VisualParseOrchestratorRuntime


def test_visual_parse_orchestrator_runtime_returns_failed_no_layout_outcome() -> None:
    runtime = VisualParseOrchestratorRuntime(
        build_text_only_result=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not build text-only")),
        finalize_no_blocks=lambda **kwargs: {},
        finalize_success=lambda **kwargs: {},
    )

    outcome = runtime.resolve_no_layout_objects(
        native_page_count=3,
        mineru_status="failed",
        runtime_limits={"profile": "default"},
        visual_method_stats={"visual_pdf_profile": "mixed_visual_pdf"},
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        visual_t0=time.perf_counter(),
        page_lines={1: ["alpha"]},
        mineru_run_meta={"status": "failed"},
    )

    assert outcome["result"] is None
    assert outcome["figure_blocks"] == []
    assert outcome["stats"]["visual_failure"] == "no_layout_objects"
    assert outcome["stats"]["chain_status"] == "failed"
    assert outcome["stats"]["mineru_run"] == {"status": "failed"}


def test_visual_parse_orchestrator_runtime_returns_text_only_no_layout_outcome() -> None:
    runtime = VisualParseOrchestratorRuntime(
        build_text_only_result=lambda **kwargs: (
            "markdown",
            {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
            [],
            {"visual_mode": "text_only"},
        ),
        finalize_no_blocks=lambda **kwargs: {},
        finalize_success=lambda **kwargs: {},
    )

    outcome = runtime.resolve_no_layout_objects(
        native_page_count=1,
        mineru_status="ok",
        runtime_limits={},
        visual_method_stats={"visual_pdf_profile": "office_text_pdf"},
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        visual_t0=time.perf_counter(),
        page_lines={1: ["alpha"]},
        mineru_run_meta={"status": "ok"},
    )

    assert outcome["result"] == ("markdown", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [])
    assert outcome["stats"] == {"visual_mode": "text_only"}
    assert outcome["figure_blocks"] == []


def test_visual_parse_orchestrator_runtime_builds_no_selected_stats_when_text_only_unavailable() -> None:
    runtime = VisualParseOrchestratorRuntime(
        build_text_only_result=lambda **kwargs: None,
        finalize_no_blocks=lambda **kwargs: {},
        finalize_success=lambda **kwargs: {},
    )

    outcome = runtime.resolve_no_selected_objects(
        native_page_count=2,
        object_count=4,
        runtime_limits={"profile": "default"},
        visual_method_stats={"visual_pdf_profile": "mixed_visual_pdf"},
        object_selection_stats={"visual_selected_object_count": 0},
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        select_ms=13,
        visual_t0=time.perf_counter(),
        page_lines={1: ["alpha"]},
        mineru_run_meta={"status": "ok"},
    )

    assert outcome["result"] is None
    assert outcome["stats"]["visual_failure"] == "no_selected_objects"
    assert outcome["stats"]["visual_selected_object_count"] == 0
    assert outcome["stats"]["visual_phase_ms"]["object_select_ms"] == 13


def test_visual_parse_orchestrator_runtime_finalizes_no_blocks_outcome() -> None:
    runtime = VisualParseOrchestratorRuntime(
        build_text_only_result=lambda **kwargs: None,
        finalize_no_blocks=lambda **kwargs: {"stats": {"visual_failure": "no_visual_blocks"}},
        finalize_success=lambda **kwargs: {},
    )

    outcome = runtime.finalize_parse(
        parts=['<ref id="p1_c1">alpha</ref>'],
        bbox_map={"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        table_blocks=[],
        figure_blocks=[],
        native_page_count=1,
        selected_objects=[],
        objects=[],
        runtime_limits={},
        visual_method_stats={},
        selected_table_candidates=0,
        selected_figure_candidates=0,
        object_selection_stats={},
        table_source="pdf_mineru",
        figure_source="pdf_mineru",
        vision_jobs=[],
        vision_job_error_count=0,
        vision_serial_recovery_retry_count=0,
        vision_serial_recovery_success_count=0,
        figure_refine_grants=0,
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        select_ms=13,
        table_crop_ms=14,
        table_vision_ms=15,
        figure_crop_ms=16,
        figure_vision_ms=17,
        visual_vision_wall_ms=18,
        visual_t0=time.perf_counter(),
        page_lines={1: ["alpha"]},
        vision_ready=False,
        vision_candidate_count=0,
        vision_attempted_count=0,
        vision_success_count=0,
        vision_empty_count=0,
        mineru_run_meta={},
    )

    assert outcome["result"] == (
        '<ref id="p1_c1">alpha</ref>',
        {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        [],
    )
    assert outcome["stats"] == {"visual_failure": "no_visual_blocks"}
    assert outcome["figure_blocks"] == []


def test_visual_parse_orchestrator_runtime_finalizes_success_outcome() -> None:
    runtime = VisualParseOrchestratorRuntime(
        build_text_only_result=lambda **kwargs: None,
        finalize_no_blocks=lambda **kwargs: {},
        finalize_success=lambda **kwargs: {
            "table_blocks": [{"table_id": "t1"}],
            "figure_blocks": [{"figure_id": "f1"}],
            "stats": {"visual_table_count": 1, "visual_figure_count": 1},
        },
    )

    outcome = runtime.finalize_parse(
        parts=['<ref id="p1_c1">alpha</ref>', '<ref id="p1_c2">beta</ref>'],
        bbox_map={"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        table_blocks=[{"table_id": "raw"}],
        figure_blocks=[{"figure_id": "raw"}],
        native_page_count=1,
        selected_objects=[{"id": "a"}],
        objects=[{"id": "a"}],
        runtime_limits={},
        visual_method_stats={},
        selected_table_candidates=1,
        selected_figure_candidates=1,
        object_selection_stats={},
        table_source="pdf_mineru_vision",
        figure_source="pdf_mineru_vision",
        vision_jobs=[{"index": 0}],
        vision_job_error_count=0,
        vision_serial_recovery_retry_count=0,
        vision_serial_recovery_success_count=0,
        figure_refine_grants=1,
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        select_ms=13,
        table_crop_ms=14,
        table_vision_ms=15,
        figure_crop_ms=16,
        figure_vision_ms=17,
        visual_vision_wall_ms=18,
        visual_t0=time.perf_counter(),
        page_lines={1: ["alpha"]},
        vision_ready=True,
        vision_candidate_count=1,
        vision_attempted_count=1,
        vision_success_count=1,
        vision_empty_count=0,
        mineru_run_meta={"status": "ok"},
    )

    assert outcome["result"] == (
        '<ref id="p1_c1">alpha</ref>\n<ref id="p1_c2">beta</ref>',
        {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        [{"table_id": "t1"}],
    )
    assert outcome["stats"]["visual_table_count"] == 1
    assert outcome["figure_blocks"] == [{"figure_id": "f1"}]
