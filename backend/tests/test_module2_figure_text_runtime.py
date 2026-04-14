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


figure_text_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "figure_semantics.py"],
    "_smart_doc_flow_module2_figure_semantics_for_text_runtime",
)

FigureTextRuntime = figure_text_module.FigureTextRuntime


def _build_runtime() -> FigureTextRuntime:
    return FigureTextRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
        header_token_is_generic=lambda text: str(text or "").strip().lower() in {"", "value", "metric", "category"},
    )


def test_figure_text_runtime_counts_markers_in_english_and_chinese() -> None:
    assert FigureTextRuntime.count_figure_markers_in_text("Figure 1 and 图2") == 2


def test_figure_text_runtime_strips_caption_prefix_and_unit_suffix() -> None:
    runtime = _build_runtime()

    result = runtime.strip_figure_caption_noise("Revenue trend (unit: %)")

    assert result == "Revenue trend"


def test_figure_text_runtime_identifies_low_signal_cases() -> None:
    runtime = _build_runtime()

    assert runtime.figure_text_is_low_signal("unit: kg") is True
    assert runtime.figure_text_is_low_signal("the image contains the text unit: kg") is True
    assert runtime.figure_text_is_low_signal("Figure 1") is True
    assert runtime.figure_text_is_low_signal("Revenue trend") is False
