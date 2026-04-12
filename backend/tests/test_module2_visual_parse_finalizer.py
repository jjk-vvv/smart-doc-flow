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


visual_parse_finalizer_module = _load_module(
    ["module2", "app", "core", "visual", "visual_parse_orchestrator.py"],
    "_smart_doc_flow_module2_visual_parse_finalizer",
)

VisualParseFinalizerRuntime = visual_parse_finalizer_module.VisualParseFinalizerRuntime


class _FakeVision:
    def get_stats_snapshot(self):
        return {"calls": 3}

    def get_last_debug(self):
        return {"last_kind": "figure"}


def _build_runtime(*, table_merge_enable: bool = True) -> VisualParseFinalizerRuntime:
    return VisualParseFinalizerRuntime(
        table_merge_enable=table_merge_enable,
        visual_vision_concurrency=4,
        default_figure_refine_budget=3,
        build_visual_parse_status_fields=lambda **kwargs: {
            "status_marker": kwargs["visual_mode"],
            "visual_selected_object_count": kwargs["selected_object_count"],
        },
        merge_same_page_tables=lambda blocks: [dict(item, merged_same=True) for item in blocks],
        merge_cross_page_tables=lambda blocks: [dict(item, merged_cross=True) for item in blocks],
        prune_fragment_tables=lambda blocks: [dict(item, pruned=True) for item in blocks],
        merge_figure_blocks=lambda left, right: left + [dict(item, merged_figures=True) for item in right],
    )


def test_visual_parse_finalizer_runtime_finalize_no_blocks_builds_artifact_stats() -> None:
    runtime = _build_runtime()
    visual_t0 = time.perf_counter()

    result = runtime.finalize_no_blocks(
        native_page_count=2,
        selected_objects=[{"id": "a"}],
        objects=[{"id": "a"}, {"id": "b"}],
        runtime_limits={"figure_refine_budget": 2},
        visual_method_stats={"visual_pdf_profile": "mixed_visual_pdf"},
        selected_table_candidates=1,
        selected_figure_candidates=1,
        object_selection_stats={"visual_selected_object_count": 1},
        vision_jobs=[{"index": 0}],
        vision_job_error_count=1,
        vision_serial_recovery_retry_count=1,
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
        visual_t0=visual_t0,
        page_lines={1: ["alpha", "beta"], 2: ["gamma"]},
        vision_ready=True,
        vision_candidate_count=2,
        vision_attempted_count=1,
        vision_success_count=0,
        vision_empty_count=1,
        mineru_run_meta={"status": "ok", "content_list_item_count": 4},
        vision=_FakeVision(),
    )

    stats = result["stats"]
    assert stats["visual_failure"] == "no_visual_blocks"
    assert stats["visual_vision_job_count"] == 1
    assert stats["visual_figure_refine_slots_total"] == 2
    assert stats["visual_figure_refine_slots_used"] == 1
    assert stats["status_marker"] == "artifact_only"
    assert stats["visual_vision_stats"] == {"calls": 3}
    assert stats["visual_vision_last_debug"] == {"last_kind": "figure"}
    assert stats["mineru_run"] == {"status": "ok", "content_list_item_count": 4}


def test_visual_parse_finalizer_runtime_finalize_success_postprocesses_blocks_and_stats() -> None:
    runtime = _build_runtime()
    visual_t0 = time.perf_counter()

    result = runtime.finalize_success(
        native_page_count=3,
        selected_objects=[{"id": "a"}, {"id": "b"}],
        objects=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        runtime_limits={"figure_refine_budget": 5},
        visual_method_stats={"visual_pdf_profile": "mixed_visual_pdf"},
        selected_table_candidates=2,
        selected_figure_candidates=1,
        object_selection_stats={"visual_selected_object_count": 2},
        bbox_map={"r1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        table_source="pdf_mineru_gemini",
        figure_source="pdf_mineru_gemini",
        vision_jobs=[{"index": 0}, {"index": 1}],
        vision_job_error_count=0,
        vision_serial_recovery_retry_count=1,
        vision_serial_recovery_success_count=1,
        figure_refine_grants=2,
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        select_ms=13,
        table_crop_ms=14,
        table_vision_ms=15,
        figure_crop_ms=16,
        figure_vision_ms=17,
        visual_vision_wall_ms=18,
        visual_t0=visual_t0,
        page_lines={1: ["alpha"], 2: ["beta"]},
        vision_ready=True,
        vision_candidate_count=3,
        vision_attempted_count=2,
        vision_success_count=2,
        vision_empty_count=0,
        mineru_run_meta={"status": "ok", "images_count": 2},
        vision=_FakeVision(),
    )

    stats = result["stats"]
    assert len(result["table_blocks"]) == 1
    assert result["table_blocks"][0]["merged_same"] is True
    assert result["table_blocks"][0]["merged_cross"] is True
    assert result["table_blocks"][0]["pruned"] is True
    assert len(result["figure_blocks"]) == 1
    assert result["figure_blocks"][0]["merged_figures"] is True
    assert stats["visual_ref_count"] == 1
    assert stats["visual_table_count"] == 1
    assert stats["visual_figure_count"] == 1
    assert stats["status_marker"] == "visual_blocks"
    assert stats["visual_vision_serial_recovery_retry_count"] == 1
    assert stats["visual_vision_serial_recovery_success_count"] == 1
    assert "postprocess_ms" in stats["visual_phase_ms"]
