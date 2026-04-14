from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_image_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_image_bootstrap_runtime")

ParserImageBundleRuntime = parser_image_bundle_runtime_module.ParserImageBundleRuntime


def test_parser_image_bundle_runtime_builds_image_ocr_and_document_kwargs() -> None:
    runtime = ParserImageBundleRuntime()

    set_runtime_page_count = lambda count: count
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)
    normalize_text = lambda text: str(text).strip()
    normalize_box = lambda box, width, height: (0.1, 0.2, 0.3, 0.4)
    visual_backend_available = lambda: (True, "")
    resolve_api_key = lambda: "api-key"
    get_ocr_engine = lambda: object()
    collect_page_ocr = lambda **kwargs: (["part"], {}, {1: ["line"]}, {1: [{"text": "cell"}]})
    build_parse_result = lambda **kwargs: ([{"table_id": "t1"}], [{"figure_id": "f1"}])

    image_ocr_kwargs = runtime.build_image_ocr_kwargs(
        max_pages_visual=8,
        set_runtime_page_count=set_runtime_page_count,
        append_ref=append_ref,
        normalize_text=normalize_text,
        normalize_box=normalize_box,
    )
    image_document_kwargs = runtime.build_image_document_kwargs(
        enable_gemini_vision_enhance=True,
        visual_backend_available=visual_backend_available,
        resolve_api_key=resolve_api_key,
        get_ocr_engine=get_ocr_engine,
        collect_page_ocr=collect_page_ocr,
        build_parse_result=build_parse_result,
    )

    assert image_ocr_kwargs["max_pages_visual"] == 8
    assert image_ocr_kwargs["set_runtime_page_count"](5) == 5
    assert image_ocr_kwargs["normalize_text"]("  v  ") == "v"
    assert image_ocr_kwargs["normalize_box"](None, 100, 200) == (0.1, 0.2, 0.3, 0.4)
    assert image_document_kwargs["enable_gemini_vision_enhance"] is True
    assert image_document_kwargs["visual_backend_available"]() == (True, "")
    assert image_document_kwargs["resolve_api_key"]() == "api-key"
    assert image_document_kwargs["get_ocr_engine"]() is not None
    assert image_document_kwargs["collect_page_ocr"]() == (["part"], {}, {1: ["line"]}, {1: [{"text": "cell"}]})
    assert image_document_kwargs["build_parse_result"]() == ([{"table_id": "t1"}], [{"figure_id": "f1"}])


def test_parser_image_bundle_runtime_builds_image_vision_and_parse_kwargs() -> None:
    runtime = ParserImageBundleRuntime()

    resolve_api_key = lambda: "api-key"
    select_low_quality_pages_for_vision = lambda page_lines, tables: [1]
    vision_focus_from_page_lines = lambda lines: "table"
    render_page_png_for_vision = lambda page: b"png"
    extract_payload = lambda image_png, focus: {"tables": [], "figures": []}
    extract_vision_insights = lambda payload, page_no, bbox_map: [("ref1", "insight")]
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)
    build_tables_from_vision_payload = lambda **kwargs: ([{"table_id": "t1"}], 2)
    build_figures_from_vision_payload = lambda **kwargs: ([{"figure_id": "f1"}], 3)
    merge_figure_blocks = lambda current, extra: current + extra
    augment_with_line_tables = lambda current, extra: current + extra
    next_table_index = lambda tables, prefix: 2
    next_figure_index = lambda figures, prefix: 3
    infer_tables_from_ocr_cells = lambda page_cells: [{"table_id": "ocr"}]
    infer_tables_from_page_lines = lambda page_lines, parts, bbox_map, source: [{"table_id": "lines"}]
    infer_figures_from_page_lines = lambda page_lines, parts, bbox_map, source, last: [{"figure_id": "line_fig"}]
    enhance_low_quality_pages_with_gemini_vision = lambda **kwargs: (
        [{"table_id": "vision"}],
        [{"figure_id": "vision_fig"}],
    )
    prune_fragment_tables = lambda tables: tables

    image_vision_kwargs = runtime.build_image_vision_kwargs(
        enabled=True,
        gemini_vision_max_pages=6,
        gemini_vision_consecutive_fail_stop=2,
        resolve_api_key=resolve_api_key,
        select_low_quality_pages_for_vision=select_low_quality_pages_for_vision,
        vision_focus_from_page_lines=vision_focus_from_page_lines,
        render_page_png_for_vision=render_page_png_for_vision,
        extract_payload=extract_payload,
        extract_vision_insights=extract_vision_insights,
        append_ref=append_ref,
        build_tables_from_vision_payload=build_tables_from_vision_payload,
        build_figures_from_vision_payload=build_figures_from_vision_payload,
        merge_figure_blocks=merge_figure_blocks,
        augment_with_line_tables=augment_with_line_tables,
        next_table_index=next_table_index,
        next_figure_index=next_figure_index,
    )
    image_parse_kwargs = runtime.build_image_parse_kwargs(
        infer_tables_from_ocr_cells=infer_tables_from_ocr_cells,
        infer_tables_from_page_lines=infer_tables_from_page_lines,
        infer_figures_from_page_lines=infer_figures_from_page_lines,
        enhance_low_quality_pages_with_gemini_vision=enhance_low_quality_pages_with_gemini_vision,
        merge_figure_blocks=merge_figure_blocks,
        prune_fragment_tables=prune_fragment_tables,
    )

    assert image_vision_kwargs["enabled"] is True
    assert image_vision_kwargs["gemini_vision_max_pages"] == 6
    assert image_vision_kwargs["gemini_vision_consecutive_fail_stop"] == 2
    assert image_vision_kwargs["resolve_api_key"]() == "api-key"
    assert image_vision_kwargs["select_low_quality_pages_for_vision"]({1: ["line"]}, []) == [1]
    assert image_vision_kwargs["vision_focus_from_page_lines"](["a", "b"]) == "table"
    assert image_vision_kwargs["render_page_png_for_vision"](object()) == b"png"
    assert image_vision_kwargs["extract_payload"](b"png", "table") == {"tables": [], "figures": []}
    assert image_vision_kwargs["extract_vision_insights"]({}, 1, {}) == [("ref1", "insight")]
    assert image_vision_kwargs["build_tables_from_vision_payload"]() == ([{"table_id": "t1"}], 2)
    assert image_vision_kwargs["build_figures_from_vision_payload"]() == ([{"figure_id": "f1"}], 3)
    assert image_vision_kwargs["merge_figure_blocks"]([{"figure_id": "a"}], [{"figure_id": "b"}]) == [
        {"figure_id": "a"},
        {"figure_id": "b"},
    ]
    assert image_vision_kwargs["augment_with_line_tables"]([{"table_id": "a"}], [{"table_id": "b"}]) == [
        {"table_id": "a"},
        {"table_id": "b"},
    ]
    assert image_vision_kwargs["next_table_index"]([], "img_t") == 2
    assert image_vision_kwargs["next_figure_index"]([], "img_f") == 3
    assert image_parse_kwargs["infer_tables_from_ocr_cells"]({1: []}) == [{"table_id": "ocr"}]
    assert image_parse_kwargs["infer_tables_from_page_lines"]({}, [], {}, "image") == [{"table_id": "lines"}]
    assert image_parse_kwargs["infer_figures_from_page_lines"]({}, [], {}, "image", []) == [{"figure_id": "line_fig"}]
    assert image_parse_kwargs["enhance_low_quality_pages_with_gemini_vision"]() == (
        [{"table_id": "vision"}],
        [{"figure_id": "vision_fig"}],
    )
    assert image_parse_kwargs["prune_fragment_tables"]([{"table_id": "keep"}]) == [{"table_id": "keep"}]
