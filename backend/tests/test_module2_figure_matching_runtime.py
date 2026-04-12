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


figure_matching_module = _load_module(
    ["module2", "app", "core", "visual", "figure_semantics.py"],
    "_smart_doc_flow_module2_figure_semantics_for_matching_runtime",
)

FigureMatchingRuntime = figure_matching_module.FigureMatchingRuntime


def _build_runtime() -> FigureMatchingRuntime:
    return FigureMatchingRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
        normalize_token_for_compare=lambda text: "".join(ch.lower() for ch in str(text or "") if ch.isalnum()),
    )


def test_figure_matching_runtime_finds_best_caption_match() -> None:
    runtime = _build_runtime()

    result = runtime.find_matching_pdf_figure_index(
        chart_title="Figure 2 Revenue Trend",
        figure_blocks=[
            {"caption": "Figure 1 Cost Breakdown"},
            {"caption": "Figure 2 Revenue Trend"},
            {"caption": "Appendix Notes"},
        ],
    )

    assert result == 1


def test_figure_matching_runtime_uses_marker_and_overlap_for_partial_match() -> None:
    runtime = _build_runtime()

    result = runtime.find_matching_pdf_figure_index(
        chart_title="Figure 7 Sales by Region",
        figure_blocks=[
            {"caption": "Figure 7 Regional Sales Overview"},
            {"caption": "Figure 8 Cash Flow"},
        ],
    )

    assert result == 0


def test_figure_matching_runtime_returns_none_for_low_signal_candidates() -> None:
    runtime = _build_runtime()

    result = runtime.find_matching_pdf_figure_index(
        chart_title="Revenue Trend",
        figure_blocks=[
            {"caption": "Appendix A"},
            {"caption": "Overview"},
        ],
    )

    assert result is None


def test_figure_matching_runtime_extracts_english_and_chinese_markers() -> None:
    assert FigureMatchingRuntime.extract_figure_marker("Figure 12 Revenue Trend") == "12"
    assert FigureMatchingRuntime.extract_figure_marker("图8 区域销售") == "8"
