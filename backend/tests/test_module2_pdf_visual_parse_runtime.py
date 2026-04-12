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


pdf_visual_parse_runtime_module = _load_module(
    ["module2", "app", "core", "pdf", "pdf_visual_parse_runtime.py"],
    "_smart_doc_flow_module2_pdf_visual_parse_runtime",
)

PdfVisualParseRuntime = pdf_visual_parse_runtime_module.PdfVisualParseRuntime


class _FakeVision:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready
        self.reset_called = False

    def reset_stats(self) -> None:
        self.reset_called = True


def test_pdf_visual_parse_runtime_returns_no_layout_outcome() -> None:
    vision = _FakeVision(ready=True)
    runtime = PdfVisualParseRuntime(
        bootstrap=lambda **kwargs: {
            "native_page_count": 2,
            "objects": [],
            "mineru_page_lines": {1: ["alpha"]},
            "layout_extract_ms": 12,
            "mineru_run_meta": {"status": "empty"},
            "mineru_status": "empty",
            "runtime_limits": {"page_cap": 10},
            "visual_method_stats": {"profile": "mixed_visual_pdf"},
        },
        prepare_context=lambda **kwargs: {
            "page_lines": {1: ["alpha"]},
            "native_context_ms": 3,
            "merge_context_ms": 4,
        },
        build_initial_refs=lambda **kwargs: {},
        prioritize_layout_objects=lambda *args, **kwargs: ([], {}),
        execute_visual=lambda **kwargs: {},
        resolve_no_layout_objects=lambda **kwargs: {"result": ("md", {}, []), "stats": {"mode": "no_layout"}},
        resolve_no_selected_objects=lambda **kwargs: {"result": ("md", {}, []), "stats": {"mode": "no_selected"}},
        finalize_parse=lambda **kwargs: {"result": ("md", {}, []), "stats": {"mode": "finalized"}},
    )

    result = runtime.parse_pdf_visual_first(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        reader=object(),
        page_count=2,
        layout_extractor=object(),
        vision=vision,
    )

    assert vision.reset_called is True
    assert result["mineru_run_meta"] == {"status": "empty"}
    assert result["outcome"]["stats"]["mode"] == "no_layout"


def test_pdf_visual_parse_runtime_finalizes_selected_objects() -> None:
    vision = _FakeVision(ready=False)
    runtime = PdfVisualParseRuntime(
        bootstrap=lambda **kwargs: {
            "native_page_count": 2,
            "objects": [{"id": "o1"}],
            "mineru_page_lines": {1: ["alpha"]},
            "layout_extract_ms": 12,
            "mineru_run_meta": {"status": "ok"},
            "mineru_status": "ok",
            "runtime_limits": {"page_cap": 10},
            "visual_method_stats": {"profile": "mixed_visual_pdf"},
        },
        prepare_context=lambda **kwargs: {
            "native_page_chunks": {1: ["chunk"]},
            "page_lines": {1: ["alpha"]},
            "native_context_ms": 3,
            "merge_context_ms": 4,
        },
        build_initial_refs=lambda **kwargs: {
            "parts": ['<ref id="p1_c1">alpha</ref>'],
            "bbox_map": {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
            "page_dims": {1: (100.0, 200.0)},
        },
        prioritize_layout_objects=lambda *args, **kwargs: ([{"id": "o1"}], {"selected": 1}),
        execute_visual=lambda **kwargs: {
            "table_blocks": [{"table_id": "pdf_mineru_t1"}],
            "figure_blocks": [{"figure_id": "pdf_mineru_f1"}],
            "selected_table_candidates": 1,
            "selected_figure_candidates": 1,
        },
        resolve_no_layout_objects=lambda **kwargs: {"result": ("md", {}, []), "stats": {"mode": "no_layout"}},
        resolve_no_selected_objects=lambda **kwargs: {"result": ("md", {}, []), "stats": {"mode": "no_selected"}},
        finalize_parse=lambda **kwargs: {"result": ("md", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, []), "stats": {"mode": "finalized"}},
    )

    result = runtime.parse_pdf_visual_first(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        reader=object(),
        page_count=2,
        layout_extractor=object(),
        vision=vision,
    )

    assert vision.reset_called is False
    assert result["mineru_run_meta"] == {"status": "ok"}
    assert result["outcome"]["stats"]["mode"] == "finalized"
