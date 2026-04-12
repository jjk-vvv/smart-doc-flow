from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


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


visual_payload_builder_module = _load_module(
    ["module2", "app", "core", "visual", "visual_payload_builder.py"],
    "_smart_doc_flow_module2_visual_payload_builder",
)

VisualBboxRuntime = visual_payload_builder_module.VisualBboxRuntime


def test_visual_bbox_runtime_normalizes_relative_bbox() -> None:
    result = VisualBboxRuntime.layout_bbox_to_ref_bbox(
        page_no=2,
        raw_bbox=[0.1, 0.2, 0.6, 0.7],
        page_dims={2: (1000.0, 800.0)},
    )

    assert result == [2.0, 0.1, 0.2, 0.5, 0.5]


def test_visual_bbox_runtime_rescales_oversized_absolute_bbox() -> None:
    result = VisualBboxRuntime.layout_bbox_to_ref_bbox(
        page_no=1,
        raw_bbox=[100.0, 200.0, 2000.0, 1600.0],
        page_dims={1: (1000.0, 800.0)},
    )

    assert result == [1.0, 0.05, 0.125, 0.95, 0.875]


def test_visual_bbox_runtime_falls_back_for_invalid_bbox() -> None:
    result = VisualBboxRuntime.layout_bbox_to_ref_bbox(
        page_no=3,
        raw_bbox="invalid",
        page_dims={3: (1000.0, 800.0)},
    )

    assert result == [3.0, 0.0, 0.0, 1.0, 1.0]


def test_visual_bbox_runtime_normalizes_ocr_polygon() -> None:
    result = VisualBboxRuntime.normalize_ocr_box(
        box=[[10, 20], [70, 20], [70, 80], [10, 80]],
        width=100,
        height=200,
    )

    assert result == pytest.approx((0.1, 0.1, 0.6, 0.3))
