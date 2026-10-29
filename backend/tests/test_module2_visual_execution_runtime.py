from __future__ import annotations

import importlib.util
import sys
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


visual_execution_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_execution_runtime.py"],
    "_smart_doc_flow_module2_visual_execution_runtime",
)

VisualExecutionRuntime = visual_execution_module.VisualExecutionRuntime


def test_visual_execution_runtime_skips_runner_when_no_jobs() -> None:
    runner_called = {"value": False}
    materialize_args = {}

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: {
            "vision_jobs": [],
            "vision_candidate_count": 0,
            "table_crop_ms": 1,
            "figure_crop_ms": 2,
            "figure_refine_grants": 0,
        },
        run_visual_vision_jobs=lambda **kwargs: runner_called.__setitem__("value", True) or {},
        materialize_visual_results=lambda **kwargs: materialize_args.update(kwargs) or {
            "table_blocks": [],
            "figure_blocks": [],
        },
        extract_native_tables_with_fitz=lambda **kwargs: [{"table_id": "pdf_fitz_t1"}],
    )

    result = runtime.execute(
        selected_objects=[],
        object_selection_stats={"visual_selected_table_candidates": 1, "visual_selected_figure_candidates": 2},
        file_name="report.pdf",
        file_bytes=b"pdf",
        page_lines={1: ["alpha"]},
        parts=[],
        bbox_map={},
        page_dims={1: (1.0, 1.0)},
        runtime_limits={},
        vision=object(),
        vision_ready=False,
    )

    assert runner_called["value"] is False
    assert result["table_source"] == "pdf_mineru"
    assert result["figure_source"] == "pdf_mineru"
    assert result["runtime_table_max_per_page"] == 2
    assert result["runtime_figure_max_per_page"] == 3
    assert result["selected_table_candidates"] == 1
    assert result["selected_figure_candidates"] == 2
    assert materialize_args["vision_results"] == {}
    assert materialize_args["table_source"] == "pdf_mineru"


def test_visual_execution_runtime_uses_runtime_limits_and_passes_runner_results() -> None:
    plan_args = {}
    run_args = {}
    materialize_args = {}

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: plan_args.update(kwargs) or {
            "vision_jobs": [{"index": 0, "kind": "table"}],
            "vision_candidate_count": 5,
            "table_crop_ms": 6,
            "figure_crop_ms": 7,
            "figure_refine_grants": 1,
        },
        run_visual_vision_jobs=lambda **kwargs: run_args.update(kwargs) or {
            0: {"index": 0, "kind": "table", "payload": {"rows": [["A"]]}, "attempted": True, "elapsed_ms": 8}
        },
        materialize_visual_results=lambda **kwargs: materialize_args.update(kwargs) or {
            "table_blocks": [{"table_id": "t1"}],
            "figure_blocks": [{"figure_id": "f1"}],
            "table_vision_ms": 8,
            "figure_vision_ms": 9,
            "vision_attempted_count": 1,
            "vision_success_count": 1,
            "vision_empty_count": 0,
            "vision_job_error_count": 0,
            "vision_serial_recovery_retry_count": 0,
            "vision_serial_recovery_success_count": 0,
        },
        extract_native_tables_with_fitz=None,
    )

    result = runtime.execute(
        selected_objects=[{"object_type": "table"}],
        object_selection_stats={},
        file_name="report.pdf",
        file_bytes=b"pdf",
        page_lines={1: ["alpha"]},
        parts=[],
        bbox_map={},
        page_dims={1: (1.0, 1.0)},
        runtime_limits={
            "table_max_per_page": 9,
            "figure_max_per_page": 8,
            "figure_refine_budget": 7,
            "figure_refine_min_score": 66,
        },
        vision="vision-service",
        vision_ready=True,
    )

    assert plan_args["runtime_figure_max_per_page"] == 8
    assert plan_args["figure_refine_budget"] == 7
    assert plan_args["figure_refine_min_score"] == 66
    assert run_args["jobs"] == [{"index": 0, "kind": "table"}]
    assert run_args["vision"] == "vision-service"
    assert materialize_args["vision_results"][0]["payload"] == {"rows": [["A"]]}
    assert materialize_args["runtime_table_max_per_page"] == 9
    assert materialize_args["runtime_figure_max_per_page"] == 8
    assert materialize_args["table_source"] == "pdf_mineru_vision"
    assert run_args["runtime_vision_concurrency"] == 1
    assert result["vision_candidate_count"] == 5
    assert result["figure_refine_grants"] == 1
    assert result["runtime_vision_concurrency"] == 1
    assert result["table_blocks"] == [{"table_id": "t1"}]
    assert result["figure_blocks"] == [{"figure_id": "f1"}]


def test_visual_execution_runtime_coerces_non_dict_runner_payload_to_empty_results() -> None:
    materialize_args = {}

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: {
            "vision_jobs": [{"index": 0, "kind": "table"}],
            "vision_candidate_count": 1,
        },
        run_visual_vision_jobs=lambda **kwargs: ["unexpected"],
        materialize_visual_results=lambda **kwargs: materialize_args.update(kwargs) or {
            "table_blocks": [],
            "figure_blocks": [],
        },
        extract_native_tables_with_fitz=None,
    )

    runtime.execute(
        selected_objects=[{"object_type": "table"}],
        object_selection_stats={},
        file_name="report.pdf",
        file_bytes=b"pdf",
        page_lines={1: ["alpha"]},
        parts=[],
        bbox_map={},
        page_dims={1: (1.0, 1.0)},
        runtime_limits={},
        vision="vision-service",
        vision_ready=True,
    )

    assert materialize_args["vision_results"] == {}


def test_visual_execution_runtime_prefills_native_tables_for_large_office_text_pdf() -> None:
    plan_args = {}
    native_calls = {}

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: plan_args.update(kwargs) or {
            "vision_jobs": [{"index": 0, "kind": "figure", "page_no": 1}],
            "vision_candidate_count": 1,
            "table_crop_ms": 0,
            "figure_crop_ms": 3,
            "figure_refine_grants": 0,
        },
        run_visual_vision_jobs=lambda **kwargs: {
            0: {"index": 0, "kind": "figure", "payload": {"caption": "chart"}, "attempted": True, "elapsed_ms": 4}
        },
        materialize_visual_results=lambda **kwargs: {
            "table_blocks": [],
            "figure_blocks": [{"figure_id": "f1"}],
            "table_vision_ms": 0,
            "figure_vision_ms": 4,
            "vision_attempted_count": 1,
            "vision_success_count": 1,
            "vision_empty_count": 0,
            "vision_job_error_count": 0,
            "vision_serial_recovery_retry_count": 0,
            "vision_serial_recovery_success_count": 0,
        },
        extract_native_tables_with_fitz=lambda **kwargs: native_calls.update(kwargs) or [
            {"table_id": "pdf_fitz_t1", "source": "pdf_fitz", "page": 5},
            {"table_id": "pdf_fitz_t2", "source": "pdf_fitz", "page": 6},
        ],
    )

    result = runtime.execute(
        selected_objects=[
            {"object_type": "table", "page": 5},
            {"object_type": "table", "page": 6},
            {"object_type": "image", "page": 1},
        ],
        object_selection_stats={"visual_selected_table_candidates": 2, "visual_selected_figure_candidates": 1},
        file_name="report.pdf",
        file_bytes=b"pdf",
        page_lines={1: ["alpha"], 5: ["table"], 6: ["table"]},
        parts=[],
        bbox_map={},
        page_dims={1: (1.0, 1.0), 5: (1.0, 1.0), 6: (1.0, 1.0)},
        runtime_limits={
            "profile": "large_visual_doc",
            "visual_pdf_profile": "office_text_pdf",
            "page_count": 6,
        },
        vision="vision-service",
        vision_ready=True,
    )

    assert native_calls["page_count"] == 6
    assert [item["object_type"] for item in plan_args["selected_objects"]] == ["image"]
    assert result["table_source"] == "pdf_fitz"
    assert result["table_blocks"] == [
        {"table_id": "pdf_fitz_t1", "source": "pdf_fitz", "page": 5},
        {"table_id": "pdf_fitz_t2", "source": "pdf_fitz", "page": 6},
    ]
    assert result["native_table_prefill_count"] == 2
    assert result["native_table_prefill_page_count"] == 2
    assert result["native_table_prefill_skipped_visual_count"] == 2


def test_visual_execution_runtime_prefills_native_tables_for_large_scanned_pdf_with_dense_table_candidates() -> None:
    plan_args = {}
    native_calls = {}

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: plan_args.update(kwargs) or {
            "vision_jobs": [{"index": 0, "kind": "figure", "page_no": 1}],
            "vision_candidate_count": 1,
            "table_crop_ms": 0,
            "figure_crop_ms": 1,
            "figure_refine_grants": 0,
        },
        run_visual_vision_jobs=lambda **kwargs: {
            0: {"index": 0, "kind": "figure", "payload": {"caption": "chart"}, "attempted": True, "elapsed_ms": 3}
        },
        materialize_visual_results=lambda **kwargs: {
            "table_blocks": [],
            "figure_blocks": [{"figure_id": "f1"}],
            "table_vision_ms": 0,
            "figure_vision_ms": 3,
            "vision_attempted_count": 1,
            "vision_success_count": 1,
            "vision_empty_count": 0,
            "vision_job_error_count": 0,
            "vision_serial_recovery_retry_count": 0,
            "vision_serial_recovery_success_count": 0,
        },
        extract_native_tables_with_fitz=lambda **kwargs: native_calls.update(kwargs) or [
            {"table_id": "pdf_fitz_t1", "source": "pdf_fitz", "page": 3},
            {"table_id": "pdf_fitz_t2", "source": "pdf_fitz", "page": 4},
            {"table_id": "pdf_fitz_t3", "source": "pdf_fitz", "page": 5},
        ],
    )

    result = runtime.execute(
        selected_objects=[
            {"object_type": "table", "page": 3},
            {"object_type": "table", "page": 4},
            {"object_type": "table", "page": 5},
            {"object_type": "image", "page": 1},
        ],
        object_selection_stats={"visual_selected_table_candidates": 3, "visual_selected_figure_candidates": 1},
        file_name="scan.pdf",
        file_bytes=b"pdf",
        page_lines={1: ["alpha"], 3: ["table"], 4: ["table"], 5: ["table"]},
        parts=[],
        bbox_map={},
        page_dims={1: (1.0, 1.0), 3: (1.0, 1.0), 4: (1.0, 1.0), 5: (1.0, 1.0)},
        runtime_limits={
            "profile": "large_visual_doc",
            "visual_pdf_profile": "visual_scanned_pdf",
            "page_count": 8,
        },
        vision="vision-service",
        vision_ready=True,
    )

    assert native_calls["page_count"] == 8
    assert [item["object_type"] for item in plan_args["selected_objects"]] == ["image"]
    assert result["table_source"] == "pdf_fitz"
    assert result["native_table_prefill_count"] == 3
    assert result["native_table_prefill_skipped_visual_count"] == 3


def test_visual_execution_runtime_backfills_mineru_image_path_into_native_tables() -> None:
    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: {
            "vision_jobs": [],
            "vision_candidate_count": 0,
            "table_crop_ms": 0,
            "figure_crop_ms": 0,
            "figure_refine_grants": 0,
        },
        run_visual_vision_jobs=lambda **kwargs: {},
        materialize_visual_results=lambda **kwargs: {
            "table_blocks": [],
            "figure_blocks": [],
            "table_vision_ms": 0,
            "figure_vision_ms": 0,
            "vision_attempted_count": 0,
            "vision_success_count": 0,
            "vision_empty_count": 0,
            "vision_job_error_count": 0,
            "vision_serial_recovery_retry_count": 0,
            "vision_serial_recovery_success_count": 0,
        },
        extract_native_tables_with_fitz=lambda **kwargs: [
            {
                "table_id": "pdf_fitz_t1",
                "source": "pdf_fitz",
                "page": 5,
                "bbox_norm": [0.10, 0.20, 0.40, 0.22],
            }
        ],
    )

    result = runtime.execute(
        selected_objects=[
            {
                "object_type": "table",
                "object_subtype": "table",
                "source_object_type": "table",
                "page": 5,
                "bbox": [0.08, 0.18, 0.52, 0.43],
                "img_path": "runtime-data/module2/work/mineru/page5_table1.png",
                "caption": ["重点监测指标"],
                "footnote": ["单位：万吨"],
            }
        ],
        object_selection_stats={"visual_selected_table_candidates": 1, "visual_selected_figure_candidates": 0},
        file_name="report.pdf",
        file_bytes=b"pdf",
        page_lines={5: ["table"]},
        parts=[],
        bbox_map={},
        page_dims={5: (1000.0, 1400.0)},
        runtime_limits={
            "profile": "large_visual_doc",
            "visual_pdf_profile": "office_text_pdf",
            "page_count": 5,
        },
        vision="vision-service",
        vision_ready=False,
    )

    assert result["table_blocks"] == [
        {
            "table_id": "pdf_fitz_t1",
            "source": "pdf_fitz",
            "page": 5,
            "bbox_norm": [0.10, 0.20, 0.40, 0.22],
            "image_path": "runtime-data/module2/work/mineru/page5_table1.png",
            "artifact_subtype": "table",
            "source_object_type": "table",
            "caption": "重点监测指标",
            "notes": ["单位：万吨"],
        }
    ]


def test_visual_execution_runtime_scales_vision_concurrency_for_dense_scanned_docs() -> None:
    class _Runner:
        def __init__(self) -> None:
            self.visual_vision_concurrency = 2
            self.calls = []

        def run(self, **kwargs):
            self.calls.append(dict(kwargs))
            return {}

    runner = _Runner()

    runtime = VisualExecutionRuntime(
        default_table_max_per_page=2,
        default_figure_max_per_page=3,
        default_figure_refine_budget=4,
        default_figure_refine_min_score=55,
        plan_visual_vision_jobs=lambda **kwargs: {
            "vision_jobs": [{"index": idx, "kind": "figure", "page_no": idx + 1} for idx in range(10)],
            "vision_candidate_count": 10,
            "table_crop_ms": 0,
            "figure_crop_ms": 1,
            "figure_refine_grants": 0,
        },
        run_visual_vision_jobs=runner.run,
        materialize_visual_results=lambda **kwargs: {
            "table_blocks": [],
            "figure_blocks": [],
            "table_vision_ms": 0,
            "figure_vision_ms": 0,
            "vision_attempted_count": 0,
            "vision_success_count": 0,
            "vision_empty_count": 0,
            "vision_job_error_count": 0,
            "vision_serial_recovery_retry_count": 0,
            "vision_serial_recovery_success_count": 0,
        },
        extract_native_tables_with_fitz=None,
    )

    result = runtime.execute(
        selected_objects=[{"object_type": "image", "page": idx + 1} for idx in range(10)],
        object_selection_stats={"visual_selected_table_candidates": 0, "visual_selected_figure_candidates": 10},
        file_name="scan.pdf",
        file_bytes=b"pdf",
        page_lines={idx + 1: ["figure"] for idx in range(10)},
        parts=[],
        bbox_map={},
        page_dims={idx + 1: (1.0, 1.0) for idx in range(10)},
        runtime_limits={
            "profile": "extreme_visual_doc",
            "visual_pdf_profile": "visual_scanned_pdf",
            "page_count": 80,
            "image_object_count": 20,
            "table_object_count": 7,
        },
        vision="vision-service",
        vision_ready=True,
    )

    assert runner.calls[0]["runtime_vision_concurrency"] == 4
    assert result["runtime_vision_concurrency"] == 4
