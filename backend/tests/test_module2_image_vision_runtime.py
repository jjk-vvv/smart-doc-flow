from __future__ import annotations

import importlib.util
import sys
import types
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


image_vision_runtime_module = _load_module(
    ["module2", "app", "core", "format", "image_document_runtime.py"],
    "_smart_doc_flow_module2_image_document_runtime_for_vision",
)

ImageVisionRuntime = image_vision_runtime_module.ImageVisionRuntime


class _FakePage:
    pass


class _FakeDoc:
    def __init__(self, page_count: int):
        self.page_count = page_count
        self.closed = False

    def __len__(self):
        return self.page_count

    def load_page(self, page_idx: int):
        return _FakePage()

    def close(self):
        self.closed = True


def test_image_vision_runtime_enhances_pages_and_merges_tables(monkeypatch) -> None:
    fake_doc = _FakeDoc(page_count=1)
    monkeypatch.setitem(
        sys.modules,
        "fitz",
        types.SimpleNamespace(open=lambda **kwargs: fake_doc),
    )

    def _append_ref(parts, bbox_map, ref_id, text, bbox):
        parts.append(f'<ref id="{ref_id}">{text}</ref>')
        bbox_map[ref_id] = list(bbox)

    runtime = ImageVisionRuntime(
        enabled=True,
        gemini_vision_max_pages=3,
        gemini_vision_consecutive_fail_stop=2,
        resolve_api_key=lambda: "key",
        select_low_quality_pages_for_vision=lambda page_lines, table_blocks: [1],
        vision_focus_from_page_lines=lambda lines: "table",
        render_page_png_for_vision=lambda page: b"png",
        extract_payload=lambda image_png, focus: {"focus": focus},
        extract_vision_insights=lambda payload, page_no, bbox_map: [("vision_insight_1", "insight")],
        append_ref=_append_ref,
        build_tables_from_vision_payload=lambda **kwargs: (
            [{"table_id": f'{kwargs["source_prefix"]}_t{kwargs["table_idx"]}', "page": kwargs["page_no"]}],
            kwargs["table_idx"] + 1,
        ),
        build_figures_from_vision_payload=lambda **kwargs: (
            [{"figure_id": f'{kwargs["source_prefix"]}_f{kwargs["figure_idx"]}', "page": kwargs["page_no"]}],
            kwargs["figure_idx"] + 1,
        ),
        merge_figure_blocks=lambda left, right: left + right,
        augment_with_line_tables=lambda base_tables, vision_tables: base_tables + vision_tables,
        next_table_index=lambda table_blocks, prefix: 1,
        next_figure_index=lambda figure_blocks, prefix: 1,
    )

    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}
    base_tables = [{"table_id": "image_ocr_line_t1", "page": 1}]

    tables, figures = runtime.enhance_low_quality_pages_with_gemini_vision(
        file_bytes=b"fake",
        filetype="png",
        page_lines={1: ["table cue"]},
        table_blocks=base_tables,
        last_figure_blocks=[],
        parts=parts,
        bbox_map=bbox_map,
        source_prefix="image_gemini_vision",
    )

    assert fake_doc.closed is True
    assert len(tables) == 2
    assert tables[1]["table_id"] == "image_gemini_vision_t1"
    assert figures == [{"figure_id": "image_gemini_vision_f1", "page": 1}]
    assert parts == ['<ref id="vision_insight_1">insight</ref>']
    assert bbox_map["vision_insight_1"] == [1.0, 0.0, 0.0, 1.0, 1.0]


def test_image_vision_runtime_short_circuits_without_api_key() -> None:
    runtime = ImageVisionRuntime(
        enabled=True,
        gemini_vision_max_pages=3,
        gemini_vision_consecutive_fail_stop=2,
        resolve_api_key=lambda: "",
        select_low_quality_pages_for_vision=lambda page_lines, table_blocks: [1],
        vision_focus_from_page_lines=lambda lines: "table",
        render_page_png_for_vision=lambda page: b"png",
        extract_payload=lambda image_png, focus: {"focus": focus},
        extract_vision_insights=lambda payload, page_no, bbox_map: [("vision_insight_1", "insight")],
        append_ref=lambda parts, bbox_map, ref_id, text, bbox: None,
        build_tables_from_vision_payload=lambda **kwargs: ([], kwargs["table_idx"]),
        build_figures_from_vision_payload=lambda **kwargs: ([], kwargs["figure_idx"]),
        merge_figure_blocks=lambda left, right: left + right,
        augment_with_line_tables=lambda base_tables, vision_tables: base_tables + vision_tables,
        next_table_index=lambda table_blocks, prefix: 1,
        next_figure_index=lambda figure_blocks, prefix: 1,
    )

    base_tables = [{"table_id": "image_ocr_line_t1", "page": 1}]
    tables, figures = runtime.enhance_low_quality_pages_with_gemini_vision(
        file_bytes=b"fake",
        filetype="png",
        page_lines={1: ["table cue"]},
        table_blocks=base_tables,
        last_figure_blocks=[],
        parts=[],
        bbox_map={},
        source_prefix="image_gemini_vision",
    )

    assert tables == base_tables
    assert figures == []
