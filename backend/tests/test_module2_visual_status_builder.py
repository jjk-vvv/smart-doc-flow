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


visual_status_builder_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_parse_orchestrator.py"],
    "_smart_doc_flow_module2_visual_status_builder",
)

VisualStatusBuilderRuntime = visual_status_builder_module.VisualStatusBuilderRuntime


def test_visual_status_builder_runtime_marks_text_only_and_mineru_ready() -> None:
    runtime = VisualStatusBuilderRuntime()

    result = runtime.build_status_fields(
        visual_mode="text_only",
        layout_object_count=0,
        selected_object_count=0,
        table_count=0,
        figure_count=0,
        text_char_count=12,
        vision_ready=False,
        vision_candidate_count=0,
        vision_attempted_count=0,
        vision_success_count=0,
        vision_empty_count=0,
        mineru_run_meta={
            "status": "ok",
            "content_list_item_count": 2,
            "images_count": 1,
            "content_list_path": "content_list.json",
            "markdown_path": "out.md",
        },
    )

    assert result["chain_status"] == "success"
    assert result["artifact_status"] == "artifact_text_only"
    assert result["vision_status"] == "not_needed"
    assert result["visual_baseline_artifact_ready"] is True
    assert result["mineru_content_list_present"] is True
    assert result["mineru_markdown_present"] is True


def test_visual_status_builder_runtime_marks_partial_visual_attempts() -> None:
    runtime = VisualStatusBuilderRuntime()

    result = runtime.build_status_fields(
        visual_mode="visual_blocks",
        layout_object_count=6,
        selected_object_count=3,
        table_count=1,
        figure_count=0,
        text_char_count=40,
        vision_ready=True,
        vision_candidate_count=3,
        vision_attempted_count=3,
        vision_success_count=1,
        vision_empty_count=2,
        mineru_run_meta={"status": "failed", "content_list_item_count": 1, "images_count": 2},
    )

    assert result["chain_status"] == "success"
    assert result["artifact_status"] == "artifact_sparse"
    assert result["vision_status"] == "attempted_partial"
    assert result["visual_baseline_artifact_ready"] is True
    assert result["visual_vision_success_count"] == 1
    assert result["visual_vision_empty_count"] == 2


def test_visual_status_builder_runtime_marks_baseline_ready_when_markdown_artifact_exists() -> None:
    runtime = VisualStatusBuilderRuntime()

    result = runtime.build_status_fields(
        visual_mode="text_only",
        layout_object_count=0,
        selected_object_count=0,
        table_count=0,
        figure_count=0,
        text_char_count=48,
        vision_ready=False,
        vision_candidate_count=0,
        vision_attempted_count=0,
        vision_success_count=0,
        vision_empty_count=0,
        mineru_run_meta={
            "status": "timeout",
            "content_list_path": "content_list.json",
            "markdown_path": "out.md",
            "content_list_item_count": 1,
        },
    )

    assert result["chain_status"] == "success"
    assert result["artifact_status"] == "artifact_text_only"
    assert result["visual_baseline_artifact_ready"] is True
    assert result["mineru_content_list_present"] is True
    assert result["mineru_markdown_present"] is True


def test_visual_status_builder_runtime_marks_rich_artifacts_and_skipped_assets() -> None:
    runtime = VisualStatusBuilderRuntime()

    result = runtime.build_status_fields(
        visual_mode="visual_blocks",
        layout_object_count=9,
        selected_object_count=5,
        table_count=2,
        figure_count=2,
        text_char_count=0,
        vision_ready=True,
        vision_candidate_count=0,
        vision_attempted_count=0,
        vision_success_count=0,
        vision_empty_count=0,
        mineru_run_meta={"status": "ok", "content_list_item_count": 10, "images_count": 6},
    )

    assert result["artifact_status"] == "artifact_rich"
    assert result["vision_status"] == "skipped_no_assets"
    assert result["visual_selected_object_count"] == 5
