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
    "_smart_doc_flow_module2_visual_planning_runtime_for_page_signal",
)

VisualPageSignalRuntime = visual_planning_module.VisualPageSignalRuntime


def _looks_like_table_cue_text(text: str) -> bool:
    lower = str(text or "").lower()
    return "table" in lower or "appendix" in lower


def _looks_like_figure_cue_text(text: str) -> bool:
    lower = str(text or "").lower()
    return "figure" in lower or "chart" in lower or "diagram" in lower


def _contains_figure_marker(text: str) -> bool:
    lower = str(text or "").lower()
    return "figure" in lower or lower.startswith("fig")


def _build_runtime(*, max_pages: int = 3, min_quality: float = 0.7, enable_figures: bool = True) -> VisualPageSignalRuntime:
    return VisualPageSignalRuntime(
        gemini_vision_max_pages=max_pages,
        gemini_vision_min_table_quality=min_quality,
        gemini_vision_enable_figures=enable_figures,
        looks_like_table_cue_text=_looks_like_table_cue_text,
        looks_like_figure_cue_text=_looks_like_figure_cue_text,
        contains_figure_marker=_contains_figure_marker,
    )


def test_visual_page_signal_runtime_derives_focus_from_page_lines() -> None:
    runtime = _build_runtime()

    assert runtime.vision_focus_from_page_lines(["Figure 2. Revenue trend", "Chart overview"]) == "figure"
    assert runtime.vision_focus_from_page_lines(["Table 2 Revenue by Year", "2024 2025 2026"]) == "table"
    assert runtime.vision_focus_from_page_lines(["Table 2 Revenue", "Figure 2 trend"]) == "mixed"
    assert runtime.vision_focus_from_page_lines(["Narrative introduction only"]) == "mixed"


def test_visual_page_signal_runtime_prioritizes_weak_tables_and_neighbors() -> None:
    runtime = _build_runtime(max_pages=3, min_quality=0.7, enable_figures=True)

    result = runtime.select_low_quality_pages_for_vision(
        page_lines={
            1: ["Table 1 Summary", "2024 2025 2026"],
            2: ["Narrative text only"],
            3: ["Figure 3 Trend", "Figure 3 continued"],
            4: ["Table 4 Detail", "111 222 333"],
        },
        table_blocks=[
            {"page": 1, "quality": 0.2},
            {"page": 4, "quality": 0.9},
        ],
    )

    assert result == [1, 3, 4, 2]


def test_visual_page_signal_runtime_samples_evenly_when_no_ranked_pages() -> None:
    runtime = _build_runtime(max_pages=3, enable_figures=False)

    result = runtime.select_low_quality_pages_for_vision(
        page_lines={
            1: ["Narrative"],
            2: ["Narrative"],
            3: ["Narrative"],
            4: ["Narrative"],
            5: ["Narrative"],
        },
        table_blocks=[],
    )

    assert result == [1, 3, 5]


def test_visual_page_signal_runtime_expands_cap_for_probe_like_docs() -> None:
    runtime = _build_runtime(max_pages=2, enable_figures=False)

    result = runtime.select_low_quality_pages_for_vision(
        page_lines={
            1: ["Vision probe", "No extractable native text"],
            2: ["Vision probe", "No extractable native text"],
            3: ["Vision probe", "No extractable native text"],
            4: ["Vision probe", "No extractable native text"],
            5: ["Vision probe", "No extractable native text"],
            6: ["Vision probe", "No extractable native text"],
        },
        table_blocks=[],
    )

    assert result == [1, 2, 3, 4, 5, 6]
