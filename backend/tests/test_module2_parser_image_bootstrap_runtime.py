from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_image_bootstrap_module = import_module("app.modules.module2.core.parsers.parser_image_bootstrap_runtime")
parser_image_bundle_module = parser_image_bootstrap_module

ParserImageBootstrapRuntime = parser_image_bootstrap_module.ParserImageBootstrapRuntime
ParserImageBundleRuntime = parser_image_bundle_module.ParserImageBundleRuntime


def test_parser_image_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserImageBootstrapRuntime()

    attrs = runtime.build_image_runtime_attrs(
        parser_image_bundle_runtime=ParserImageBundleRuntime(),
        max_pages_visual=6,
        enable_gemini_vision_enhance=True,
        gemini_vision_max_pages=8,
        gemini_vision_consecutive_fail_stop=2,
        set_runtime_page_count=lambda count: None,
        visual_backend_available=lambda: (True, ""),
        resolve_api_key=lambda: "test-key",
        get_ocr_engine=lambda: object(),
        normalize_text=lambda text: str(text).strip(),
        select_low_quality_pages_for_vision=lambda page_lines, table_blocks: [1],
        vision_focus_from_page_lines=lambda lines: "focus",
        render_page_png_for_vision=lambda page: b"png",
        extract_payload=lambda image_png, focus: {"tables": [], "figures": []},
        extract_vision_insights=lambda payload, page_no, bbox_map: [],
        build_tables_from_vision_payload=lambda **kwargs: ([], kwargs["table_idx"]),
        build_figures_from_vision_payload=lambda **kwargs: ([], kwargs["figure_idx"]),
        infer_tables_from_ocr_cells=lambda page_cells: [],
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source_prefix: [],
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source_prefix, last_figure_blocks: [],
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: ([], []),
        merge_figure_blocks=lambda figure_blocks, vision_figures: list(figure_blocks or []) + list(vision_figures or []),
        augment_with_line_tables=lambda table_blocks, vision_tables: list(table_blocks or []) + list(vision_tables or []),
        prune_fragment_tables=lambda table_blocks: list(table_blocks or []),
    )

    expected_keys = {
        "_image_ocr_runtime",
        "_image_vision_runtime",
        "_image_parse_runtime",
        "_image_document_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_image_ocr_runtime"], "collect_page_ocr")
    assert hasattr(attrs["_image_vision_runtime"], "enhance_low_quality_pages_with_gemini_vision")
    assert hasattr(attrs["_image_parse_runtime"], "build_parse_result")
    assert hasattr(attrs["_image_document_runtime"], "parse_image")
    assert attrs["_image_ocr_runtime"].max_pages_visual == 6
    assert attrs["_image_vision_runtime"].enabled is True
    assert attrs["_image_document_runtime"]._collect_page_ocr.__self__ is attrs["_image_ocr_runtime"]
    assert attrs["_image_document_runtime"]._build_parse_result.__self__ is attrs["_image_parse_runtime"]
