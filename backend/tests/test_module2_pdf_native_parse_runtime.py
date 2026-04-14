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


pdf_native_parse_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pdf", "pdf_native_parse_runtime.py"],
    "_smart_doc_flow_module2_pdf_native_parse_runtime",
)

PdfNativeParseRuntime = pdf_native_parse_runtime_module.PdfNativeParseRuntime


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, texts: list[str]) -> None:
        self.pages = [_FakePage(text) for text in texts]


def _append_ref(parts, bbox_map, ref_id, text, bbox):
    parts.append(f'<ref id="{ref_id}">{text}</ref>')
    bbox_map[ref_id] = [float(item) for item in bbox[:5]]


def test_pdf_native_parse_runtime_early_returns_ocr_on_low_probe_chars() -> None:
    runtime = PdfNativeParseRuntime(
        max_pages=10,
        max_pages_visual=20,
        visual_probe_pages=4,
        native_text_threshold=50,
        ocr_cue_scan_pages=6,
        enable_fitz_table=False,
        table_merge_enable=True,
        visual_force_ocr_on_weak_native=True,
        gemini_vision_enable_figures=True,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        split_page_text=lambda text: [text] if text else [],
        append_ref=_append_ref,
        collect_table_cue_pages=lambda reader, cue_scan_pages: [1],
        extract_pdf_tables_with_fitz=lambda *args, **kwargs: [],
        is_weak_native_table_result=lambda tables, cue_pages: False,
        select_line_augmentation_pages=lambda page_lines, base_tables, cue_pages=None: {},
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [],
        augment_with_line_tables=lambda base_tables, line_tables: base_tables + line_tables,
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source, last_figure_blocks: [],
        figure_blocks_need_vision=lambda figure_blocks: False,
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: (kwargs["table_blocks"], []),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda tables: tables,
    )
    reader = _FakeReader(["short", "tiny"])

    result = runtime.parse_pdf_native(
        reader=reader,
        file_bytes=b"%PDF",
        track="VisualTrack",
        total_pages=2,
        visual_backend_ready=True,
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert result["early_result"] == ("ocr", {}, [])


def test_pdf_native_parse_runtime_builds_native_result_and_requests_vision() -> None:
    runtime = PdfNativeParseRuntime(
        max_pages=10,
        max_pages_visual=20,
        visual_probe_pages=2,
        native_text_threshold=5,
        ocr_cue_scan_pages=6,
        enable_fitz_table=True,
        table_merge_enable=True,
        visual_force_ocr_on_weak_native=False,
        gemini_vision_enable_figures=True,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        split_page_text=lambda text: [chunk for chunk in str(text).split("\n\n") if chunk],
        append_ref=_append_ref,
        collect_table_cue_pages=lambda reader, cue_scan_pages: [1],
        extract_pdf_tables_with_fitz=lambda file_bytes, page_count, parts, bbox_map: [{"table_id": "fitz_t1"}],
        is_weak_native_table_result=lambda tables, cue_pages: True,
        select_line_augmentation_pages=lambda page_lines, base_tables, cue_pages=None: page_lines,
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [{"table_id": f"{source}_t1"}],
        augment_with_line_tables=lambda base_tables, line_tables: base_tables + line_tables,
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source, last_figure_blocks: [
            {"figure_id": "pdf_caption_f1"}
        ],
        figure_blocks_need_vision=lambda figure_blocks: True,
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: (
            kwargs["table_blocks"] + [{"table_id": "pdf_gemini_vision_native_t1"}],
            [{"figure_id": "pdf_gemini_vision_native_f1"}],
        ),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda tables: tables + [{"table_id": "pruned_marker"}],
    )
    reader = _FakeReader(["alpha\nbeta", "gamma"])

    result = runtime.parse_pdf_native(
        reader=reader,
        file_bytes=b"%PDF",
        track="VisualTrack",
        total_pages=2,
        visual_backend_ready=False,
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert "early_result" not in result
    assert "p1_c1" in result["bbox_map"]
    assert [table["table_id"] for table in result["table_blocks"]] == [
        "fitz_t1",
        "pdf_native_t1",
        "pdf_gemini_vision_native_t1",
        "pruned_marker",
    ]
    assert [figure["figure_id"] for figure in result["figure_blocks"]] == [
        "pdf_caption_f1",
        "pdf_gemini_vision_native_f1",
    ]
    assert result["stats"]["native_vision_requested"] is True
    assert "visual_backend_unavailable" in result["stats"]["native_vision_reasons"]
    assert "weak_native_tables" in result["stats"]["native_vision_reasons"]
    assert "shallow_native_figures" in result["stats"]["native_vision_reasons"]


def test_pdf_native_parse_runtime_forces_ocr_when_native_tables_stay_weak() -> None:
    runtime = PdfNativeParseRuntime(
        max_pages=10,
        max_pages_visual=20,
        visual_probe_pages=2,
        native_text_threshold=1,
        ocr_cue_scan_pages=6,
        enable_fitz_table=False,
        table_merge_enable=True,
        visual_force_ocr_on_weak_native=True,
        gemini_vision_enable_figures=False,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        split_page_text=lambda text: [text] if text else [],
        append_ref=_append_ref,
        collect_table_cue_pages=lambda reader, cue_scan_pages: [1],
        extract_pdf_tables_with_fitz=lambda *args, **kwargs: [],
        is_weak_native_table_result=lambda tables, cue_pages: True,
        select_line_augmentation_pages=lambda page_lines, base_tables, cue_pages=None: page_lines,
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [{"table_id": "pdf_native_t1"}],
        augment_with_line_tables=lambda base_tables, line_tables: base_tables + line_tables,
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source, last_figure_blocks: [],
        figure_blocks_need_vision=lambda figure_blocks: False,
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: (kwargs["table_blocks"], []),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda tables: tables,
    )
    reader = _FakeReader(["enough native text"])

    result = runtime.parse_pdf_native(
        reader=reader,
        file_bytes=b"%PDF",
        track="VisualTrack",
        total_pages=1,
        visual_backend_ready=True,
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr_fallback", {}, []),
    )

    assert result["early_result"] == ("ocr_fallback", {}, [])
