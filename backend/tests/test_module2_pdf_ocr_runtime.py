from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

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


pdf_ocr_runtime_module = _load_module(
    ["module2", "app", "core", "pdf", "pdf_ocr_runtime.py"],
    "_smart_doc_flow_module2_pdf_ocr_runtime",
)

PdfOcrRuntime = pdf_ocr_runtime_module.PdfOcrRuntime


class _FakeArray:
    def reshape(self, *shape):
        return {"shape": shape}


class _FakePixmap:
    def __init__(self, *, width: int = 8, height: int = 8, n: int = 1):
        self.width = width
        self.height = height
        self.n = n
        self.samples = b"\x00" * (width * height * n)


class _FakePage:
    def __init__(self, page_idx: int):
        self.page_idx = page_idx

    def get_pixmap(self, matrix=None, alpha: bool = False):
        return _FakePixmap()


class _FakeDoc:
    def __init__(self, page_count: int):
        self._page_count = page_count
        self.closed = False

    def __len__(self):
        return self._page_count

    def load_page(self, page_idx: int):
        return _FakePage(page_idx)

    def close(self):
        self.closed = True


def _install_fake_modules(monkeypatch, *, page_count: int = 1):
    fake_doc = _FakeDoc(page_count=page_count)
    fake_numpy = types.SimpleNamespace(uint8="uint8", frombuffer=lambda *args, **kwargs: _FakeArray())
    fake_fitz = types.SimpleNamespace(
        Matrix=lambda x, y: {"x": x, "y": y},
        open=lambda **kwargs: fake_doc,
    )
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    return fake_doc


def _build_runtime(state: dict[str, Any], *, engine_outputs: list[Any], **overrides) -> PdfOcrRuntime:
    outputs = list(engine_outputs)

    class _FakeEngine:
        def __call__(self, image):
            state["engine_calls"] = int(state.get("engine_calls", 0) or 0) + 1
            return outputs.pop(0) if outputs else ([], None)

    def _set_runtime_page_count(page_count: int) -> None:
        state["runtime_page_count"] = page_count

    config = dict(
        ocr_large_doc_dpi=120,
        ocr_large_doc_page_threshold=50,
        ocr_low_priority_dpi=96,
        ocr_high_priority_pages=3,
        ocr_dense_cue_threshold=20,
        ocr_max_attempt_pages_dense_cue=8,
        ocr_max_attempt_pages_mid_cue=6,
        ocr_dynamic_neighbor_pages=0,
        ocr_dynamic_neighbor_auto_enable=False,
        ocr_dynamic_neighbor_auto_max=0,
        ocr_min_pages_before_budget=3,
        ocr_front_scan_pages=4,
        ocr_low_cue_boost_enable=False,
        ocr_low_cue_min_pages_cap=4,
        ocr_time_budget_max_sec=30.0,
        ocr_time_budget_sec=8.0,
        ocr_time_budget_per_page=0.2,
        ocr_budget_guard_ratio=0.9,
        ocr_dynamic_early_stop_enable=False,
        ocr_dynamic_early_stop_min_pages=3,
        ocr_dynamic_early_stop_min_signal_pages=1,
        ocr_dynamic_early_stop_streak=2,
        ocr_relaxed_trigger_table_count=2,
        ocr_table_relaxed_min_quality=0.4,
        ocr_table_min_quality=0.5,
        ocr_uncovered_line_aug_pages=2,
        get_ocr_engine=lambda: _FakeEngine(),
        set_runtime_page_count=_set_runtime_page_count,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        normalize_box=lambda box, width, height: (0.1, 0.2, 0.3, 0.4),
        build_ocr_page_indices=lambda page_count, cue_pages=None: [0],
        looks_like_table_cue_text=lambda text: "table" in str(text).lower(),
        infer_tables_from_ocr_cells=lambda page_cells, **kwargs: [
            {
                "table_id": "ocr_t1",
                "source": "pdf_ocr_layout",
                "page": 1,
                "headers": ["年份", "数值"],
                "rows": [
                    {"row_index": 1, "cells": [{"col_index": 1, "text": "2024"}, {"col_index": 2, "text": "10"}]},
                    {"row_index": 2, "cells": [{"col_index": 1, "text": "2025"}, {"col_index": 2, "text": "12"}]},
                ],
                "row_count": 2,
                "col_count": 2,
                "quality": 0.72,
            }
        ],
        augment_with_line_tables=lambda base_tables, line_tables: base_tables + line_tables,
        need_line_table_augmentation=lambda table_blocks, page_lines: False,
        select_line_augmentation_pages=lambda page_lines, base_tables, cue_pages=None: {},
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [],
        select_uncovered_table_like_pages=lambda page_lines, base_tables, aggressive=False: {},
        infer_figures_from_page_lines=lambda **kwargs: [
            {"figure_id": "pdf_ocr_caption_f1", "caption": "Figure 1", "source": "pdf_ocr_caption", "page": 1}
        ],
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: (
            kwargs["table_blocks"],
            [{"figure_id": "pdf_gemini_vision_f1", "caption": "Vision Figure", "source": "pdf_gemini_vision", "page": 1}],
        ),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda table_blocks: table_blocks,
    )
    config.update(overrides)
    return PdfOcrRuntime(**config)


def test_pdf_ocr_runtime_parses_pages_and_merges_vision_figures(monkeypatch) -> None:
    fake_doc = _install_fake_modules(monkeypatch, page_count=1)
    state: dict[str, Any] = {}
    runtime = _build_runtime(
        state,
        engine_outputs=[
            (
                [
                    ([[0, 0], [1, 0], [1, 1], [0, 1]], "Table 1 metrics", 0.95),
                    ([[0, 2], [1, 2], [1, 3], [0, 3]], "2024 10 20", 0.93),
                ],
                None,
            )
        ],
        ocr_relaxed_trigger_table_count=0,
    )

    markdown, bbox_map, table_blocks, figure_blocks = runtime.parse_pdf_with_ocr(
        file_bytes=b"%PDF-1.4 fake",
        page_count=1,
        cue_pages=None,
    )

    assert state["runtime_page_count"] == 1
    assert state["engine_calls"] == 1
    assert fake_doc.closed is True
    assert 'ref id="p1_ocr1"' in markdown
    assert "p1_ocr1" in bbox_map
    assert len(table_blocks) == 1
    assert table_blocks[0]["table_id"] == "ocr_t1"
    assert len(figure_blocks) == 2
    assert figure_blocks[0]["figure_id"] == "pdf_ocr_caption_f1"
    assert figure_blocks[1]["figure_id"] == "pdf_gemini_vision_f1"


def test_pdf_ocr_runtime_raises_when_ocr_extracts_no_text(monkeypatch) -> None:
    _install_fake_modules(monkeypatch, page_count=1)
    runtime = _build_runtime(
        {},
        engine_outputs=[
            (
                [
                    ([[0, 0], [1, 0], [1, 1], [0, 1]], "", 0.1),
                ],
                None,
            )
        ],
    )

    with pytest.raises(ValueError, match="no text was extracted"):
        runtime.parse_pdf_with_ocr(
            file_bytes=b"%PDF-1.4 fake",
            page_count=1,
            cue_pages=None,
        )
