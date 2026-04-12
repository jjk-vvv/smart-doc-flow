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


visual_planning_module = _load_module(
    ["module2", "app", "core", "visual", "visual_planning_runtime.py"],
    "_smart_doc_flow_module2_visual_planning_runtime_for_layout_selector",
)

VisualLayoutSelectorRuntime = visual_planning_module.VisualLayoutSelectorRuntime


def _build_runtime(*, chart_only: bool = True, allow_fallback: bool = True) -> VisualLayoutSelectorRuntime:
    return VisualLayoutSelectorRuntime(
        visual_max_objects=12,
        visual_table_max_per_page=2,
        visual_figure_max_per_page=2,
        visual_figure_chart_score_min=4,
        visual_figure_cueless_fallback_max=1,
        visual_figure_chart_only=chart_only,
        visual_figure_allow_cueless_fallback=allow_fallback,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        safe_text_list=lambda values, max_items=8, max_len=180: [
            str(item)[:max_len]
            for item in (values if isinstance(values, list) else ([values] if values else []))
        ][:max_items],
        infer_figure_type_from_text=lambda text: (
            "chart"
            if "chart" in str(text).lower()
            else "diagram"
            if "diagram" in str(text).lower()
            else "formula"
            if "formula" in str(text).lower()
            else "photo"
        ),
        contains_table_marker=lambda text: "table" in str(text).lower(),
        contains_figure_marker=lambda text: "figure" in str(text).lower() or "chart" in str(text).lower(),
        looks_like_figure_cue_text=lambda text: "trend" in str(text).lower() or "chart" in str(text).lower(),
    )


def test_visual_layout_selector_runtime_evaluates_chart_like_candidate() -> None:
    runtime = _build_runtime(chart_only=True)

    result = runtime.evaluate_visual_figure_candidate(
        file_name="report.pdf",
        page_no=1,
        item={"caption": ["Figure 12 revenue trend chart"], "object_subtype": "image"},
        page_lines={1: ["some page text"]},
        chart_score_min=4,
    )

    assert result["chart_like"] is True
    assert result["selection_priority"] == 0
    assert result["inferred_type"] == "chart"
    assert "caption_marker" in result["reasons"]


def test_visual_layout_selector_runtime_prioritizes_page_coverage_and_table_first() -> None:
    runtime = _build_runtime(chart_only=False)

    selected, summary = runtime.prioritize_layout_objects(
        [
            {"object_type": "table", "page": 1, "caption": ["Table 1"], "area": 0.8},
            {"object_type": "image", "page": 1, "caption": ["Figure 1 chart"], "area": 0.5},
            {"object_type": "image", "page": 2, "caption": ["Figure 2 chart"], "area": 0.6},
            {"object_type": "table", "page": 2, "caption": ["Table 2"], "area": 0.7},
        ],
        file_name="report.pdf",
        page_count=2,
        page_lines={1: ["p1"], 2: ["p2"]},
        runtime_limits={"max_objects": 4, "table_max_per_page": 1, "figure_max_per_page": 1, "chart_score_min": 4},
    )

    assert len(selected) == 4
    assert str(selected[0].get("object_type")) == "table"
    assert str(selected[1].get("object_type")) == "image"
    assert str(selected[2].get("object_type")) == "table"
    assert str(selected[3].get("object_type")) == "image"
    assert summary["visual_selected_table_candidates"] == 2
    assert summary["visual_selected_figure_candidates"] == 2
    assert summary["visual_selected_table_pages"] == 2
    assert summary["visual_selected_figure_pages"] == 2


def test_visual_layout_selector_runtime_uses_cueless_fallback_when_chart_only_filters_everything() -> None:
    runtime = _build_runtime(chart_only=True, allow_fallback=True)

    selected, summary = runtime.prioritize_layout_objects(
        [
            {"object_type": "image", "page": 1, "caption": ["Plain photo"], "area": 0.4},
            {"object_type": "image", "page": 2, "caption": ["Another photo"], "area": 0.5},
        ],
        file_name="report.pdf",
        page_count=2,
        page_lines={1: ["plain page"], 2: ["another page"]},
        runtime_limits={"max_objects": 3, "figure_max_per_page": 1, "cueless_fallback_max": 1, "chart_score_min": 4},
    )

    assert len(selected) == 1
    assert str(selected[0].get("object_type")) == "image"
    assert summary["visual_figure_candidates_filtered_nonchart"] == 2
    assert summary["visual_figure_fallback_selected"] == 1


def test_visual_layout_selector_runtime_returns_empty_summary_for_no_candidates() -> None:
    runtime = _build_runtime(chart_only=True)

    selected, summary = runtime.prioritize_layout_objects(
        [{"object_type": "text", "page": 1}],
        file_name="report.pdf",
        page_count=1,
        page_lines={1: ["only text"]},
        runtime_limits={"chart_score_min": 4},
    )

    assert selected == []
    assert summary["visual_selected_table_candidates"] == 0
    assert summary["visual_selected_figure_candidates"] == 0
