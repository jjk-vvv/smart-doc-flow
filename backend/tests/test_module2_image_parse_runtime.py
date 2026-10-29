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


image_parse_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "image_document_runtime.py"],
    "_smart_doc_flow_module2_image_document_runtime_for_parse",
)

ImageParseRuntime = image_parse_runtime_module.ImageParseRuntime


def test_image_parse_runtime_builds_tables_figures_and_merges_vision() -> None:
    runtime = ImageParseRuntime(
        infer_tables_from_ocr_cells=lambda page_cells: [],
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [
            {"table_id": "image_ocr_line_t1", "source": source}
        ],
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source, last_figure_blocks: [
            {"figure_id": "image_caption_f1", "source": source}
        ],
        enhance_low_quality_pages_with_vision=lambda **kwargs: (
            kwargs["table_blocks"] + [{"table_id": "image_vision_t1", "source": kwargs["source_prefix"]}],
            [{"figure_id": "image_vision_f1", "source": kwargs["source_prefix"]}],
        ),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda table_blocks: table_blocks + [{"table_id": "pruned_marker"}],
    )

    tables, figures = runtime.build_parse_result(
        visual_backend_ready=True,
        resolved_vision_enhance=True,
        file_bytes=b"fake",
        filetype="png",
        page_lines={1: ["caption", "table row"]},
        page_cells={},
        last_figure_blocks=[],
        parts=[],
        bbox_map={},
    )

    assert [table["table_id"] for table in tables] == [
        "image_ocr_line_t1",
        "image_vision_t1",
        "pruned_marker",
    ]
    assert [figure["figure_id"] for figure in figures] == [
        "image_caption_f1",
        "image_vision_f1",
    ]


def test_image_parse_runtime_skips_ocr_tables_when_visual_backend_unavailable() -> None:
    runtime = ImageParseRuntime(
        infer_tables_from_ocr_cells=lambda page_cells: [{"table_id": "should_not_run"}],
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source: [{"table_id": "should_not_run"}],
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source, last_figure_blocks: [
            {"figure_id": "image_caption_f1", "source": source}
        ],
        enhance_low_quality_pages_with_vision=lambda **kwargs: (kwargs["table_blocks"], []),
        merge_figure_blocks=lambda left, right: left + right,
        prune_fragment_tables=lambda table_blocks: table_blocks,
    )

    tables, figures = runtime.build_parse_result(
        visual_backend_ready=False,
        resolved_vision_enhance=False,
        file_bytes=b"fake",
        filetype="png",
        page_lines={1: ["[Image page 1] OCR backend unavailable, trying Vision."]},
        page_cells={},
        last_figure_blocks=[],
        parts=[],
        bbox_map={},
    )

    assert tables == []
    assert figures == [{"figure_id": "image_caption_f1", "source": "image_caption"}]
