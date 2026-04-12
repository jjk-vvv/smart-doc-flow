from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


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


visual_planning_module = _load_module(
    ["module2", "app", "core", "visual", "visual_planning_runtime.py"],
    "_smart_doc_flow_module2_visual_planning_runtime_for_job_planner",
)

VisualJobPlannerRuntime = visual_planning_module.VisualJobPlannerRuntime


class _FakeCropper:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def load_or_crop(self, *, item: dict[str, Any], pdf_bytes: bytes, is_table: bool):
        self.calls.append(
            {
                "item": dict(item),
                "pdf_bytes": pdf_bytes,
                "is_table": is_table,
            }
        )
        if not item.get("crop_ok", True):
            return b"", "", None
        return bytes(f"{item.get('object_type', '')}-{item.get('page', '')}", "utf-8"), "image/png", None


def test_visual_job_planner_runtime_builds_table_and_figure_jobs() -> None:
    context_calls: list[dict[str, Any]] = []

    def _build_context(**kwargs):
        context_calls.append(dict(kwargs))
        return {
            "file_name": kwargs["file_name"],
            "page": kwargs["page_no"],
            "object_type": kwargs["object_type"],
        }

    runtime = VisualJobPlannerRuntime(build_visual_object_context=_build_context)
    cropper = _FakeCropper()

    result = runtime.plan_jobs(
        selected_objects=[
            {"object_type": "table", "page": 1, "crop_ok": True},
            {"object_type": "image", "page": 2, "crop_ok": True, "_visual_figure_eval": {"score": 8}},
        ],
        file_name="report.pdf",
        file_bytes=b"%PDF-1.4 fake",
        page_lines={1: ["Table page"], 2: ["Figure page"]},
        cropper=cropper,
        runtime_figure_max_per_page=2,
        figure_refine_budget=1,
        figure_refine_min_score=4,
    )

    vision_jobs = result["vision_jobs"]
    assert len(vision_jobs) == 2
    assert result["vision_candidate_count"] == 2
    assert vision_jobs[0]["index"] == 0
    assert vision_jobs[0]["kind"] == "table"
    assert vision_jobs[1]["index"] == 1
    assert vision_jobs[1]["kind"] == "figure"
    assert vision_jobs[1]["allow_refine"] is True
    assert result["figure_refine_grants"] == 1
    assert cropper.calls[0]["is_table"] is True
    assert cropper.calls[1]["is_table"] is False
    assert context_calls[0]["object_type"] == "table"
    assert context_calls[1]["object_type"] == "figure"


def test_visual_job_planner_runtime_keeps_candidate_stats_when_crop_fails_and_budget_exhausts() -> None:
    runtime = VisualJobPlannerRuntime(
        build_visual_object_context=lambda **kwargs: {"page": kwargs["page_no"], "object_type": kwargs["object_type"]}
    )
    cropper = _FakeCropper()

    result = runtime.plan_jobs(
        selected_objects=[
            {"object_type": "table", "page": 1, "crop_ok": False},
            {"object_type": "image", "page": 2, "crop_ok": True, "_visual_figure_eval": {"score": 8}},
            {"object_type": "image", "page": 3, "crop_ok": True, "_visual_figure_eval": {"score": 9}},
        ],
        file_name="report.pdf",
        file_bytes=b"%PDF-1.4 fake",
        page_lines={2: ["Figure A"], 3: ["Figure B"]},
        cropper=cropper,
        runtime_figure_max_per_page=2,
        figure_refine_budget=1,
        figure_refine_min_score=4,
    )

    vision_jobs = result["vision_jobs"]
    assert result["vision_candidate_count"] == 3
    assert len(vision_jobs) == 2
    assert result["figure_refine_grants"] == 1
    assert vision_jobs[0]["kind"] == "figure"
    assert vision_jobs[0]["allow_refine"] is True
    assert vision_jobs[1]["kind"] == "figure"
    assert vision_jobs[1]["allow_refine"] is False


def test_visual_job_planner_runtime_skips_image_jobs_when_figure_limit_disabled() -> None:
    runtime = VisualJobPlannerRuntime(
        build_visual_object_context=lambda **kwargs: {"page": kwargs["page_no"], "object_type": kwargs["object_type"]}
    )
    cropper = _FakeCropper()

    result = runtime.plan_jobs(
        selected_objects=[
            {"object_type": "image", "page": 1, "crop_ok": True, "_visual_figure_eval": {"score": 10}},
        ],
        file_name="report.pdf",
        file_bytes=b"%PDF-1.4 fake",
        page_lines={1: ["Figure only"]},
        cropper=cropper,
        runtime_figure_max_per_page=0,
        figure_refine_budget=2,
        figure_refine_min_score=4,
    )

    assert result["vision_candidate_count"] == 0
    assert result["vision_jobs"] == []
    assert cropper.calls == []


def test_visual_job_planner_runtime_uses_configured_cropper_provider_when_cropper_not_passed() -> None:
    cropper = _FakeCropper()

    runtime = VisualJobPlannerRuntime(
        build_visual_object_context=lambda **kwargs: {"page": kwargs["page_no"], "object_type": kwargs["object_type"]},
        get_cropper=lambda: cropper,
    )

    result = runtime.plan_jobs(
        selected_objects=[{"object_type": "table", "page": 1, "crop_ok": True}],
        file_name="report.pdf",
        file_bytes=b"%PDF-1.4 fake",
        page_lines={1: ["Table page"]},
        runtime_figure_max_per_page=1,
        figure_refine_budget=0,
        figure_refine_min_score=4,
    )

    assert len(result["vision_jobs"]) == 1
    assert result["vision_jobs"][0]["kind"] == "table"
    assert cropper.calls[0]["is_table"] is True
