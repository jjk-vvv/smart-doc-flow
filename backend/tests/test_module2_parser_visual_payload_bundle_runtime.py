from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_payload_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_visual_payload_bootstrap_runtime")

ParserVisualPayloadBundleRuntime = parser_visual_payload_bundle_runtime_module.ParserVisualPayloadBundleRuntime


def test_parser_visual_payload_bundle_runtime_builds_figure_kwargs() -> None:
    runtime = ParserVisualPayloadBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    figure_text_is_low_signal = lambda text: not str(text).strip()
    strip_figure_caption_noise = lambda text: str(text).replace("caption:", "").strip()
    header_token_is_generic = lambda text: str(text).lower() in {"col_1", "col_2"}
    normalize_dataframe_headers = lambda headers, **kwargs: [str(item).strip() for item in (headers or [])]
    normalize_dataframe_matrix = lambda rows, **kwargs: [
        [str(cell).strip() for cell in row]
        for row in (rows or [])
    ]
    figure_axis_dimension_label = lambda values: "dimension"
    headers_need_recovery = lambda headers: False
    recover_low_signal_headers = lambda headers, rows, **kwargs: (headers, rows)
    infer_figure_type_from_text = lambda text: "chart"
    safe_text_list = lambda items, **kwargs: [str(item).strip() for item in (items or []) if str(item).strip()]
    normalize_figure_key_values = lambda items, **kwargs: list(items or [])
    coerce_figure_dataframe = lambda **kwargs: (["A"], [["1"]], "model")
    recover_figure_title_and_caption = lambda **kwargs: ("Title", "Caption")
    to_float_or_none = lambda value: float(value) if value is not None else None
    count_figure_markers_in_text = lambda text: 1
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)
    layout_bbox_to_ref_bbox = lambda **kwargs: [1.0, 0.0, 0.0, 1.0, 1.0]

    figure_semantics_kwargs = runtime.build_figure_semantics_kwargs(
        normalize_text=normalize_text,
        figure_text_is_low_signal=figure_text_is_low_signal,
        strip_figure_caption_noise=strip_figure_caption_noise,
        header_token_is_generic=header_token_is_generic,
        normalize_dataframe_headers=normalize_dataframe_headers,
        normalize_dataframe_matrix=normalize_dataframe_matrix,
        figure_axis_dimension_label=figure_axis_dimension_label,
        headers_need_recovery=headers_need_recovery,
        recover_low_signal_headers=recover_low_signal_headers,
    )
    figure_vision_payload_kwargs = runtime.build_figure_vision_payload_kwargs(
        gemini_vision_enable_figures=True,
        gemini_vision_max_figures_per_page=4,
        gemini_vision_min_figure_quality=0.65,
        normalize_text=normalize_text,
        infer_figure_type_from_text=infer_figure_type_from_text,
        safe_text_list=safe_text_list,
        figure_text_is_low_signal=figure_text_is_low_signal,
        normalize_dataframe_headers=normalize_dataframe_headers,
        normalize_dataframe_matrix=normalize_dataframe_matrix,
        normalize_figure_key_values=normalize_figure_key_values,
        coerce_figure_dataframe=coerce_figure_dataframe,
        recover_figure_title_and_caption=recover_figure_title_and_caption,
        to_float_or_none=to_float_or_none,
        count_figure_markers_in_text=count_figure_markers_in_text,
    )
    visual_figure_builder_kwargs = runtime.build_visual_figure_builder_kwargs(
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
        infer_figure_type_from_text=infer_figure_type_from_text,
        figure_text_is_low_signal=figure_text_is_low_signal,
        normalize_dataframe_headers=normalize_dataframe_headers,
        normalize_dataframe_matrix=normalize_dataframe_matrix,
        normalize_figure_key_values=normalize_figure_key_values,
        coerce_figure_dataframe=coerce_figure_dataframe,
        recover_figure_title_and_caption=recover_figure_title_and_caption,
        count_figure_markers_in_text=count_figure_markers_in_text,
        to_float_or_none=to_float_or_none,
        append_ref=append_ref,
        layout_bbox_to_ref_bbox=layout_bbox_to_ref_bbox,
    )

    assert figure_semantics_kwargs["normalize_text"]("  x  ") == "x"
    assert figure_semantics_kwargs["figure_text_is_low_signal"]("") is True
    assert figure_semantics_kwargs["strip_figure_caption_noise"]("caption: chart") == "chart"
    assert figure_semantics_kwargs["header_token_is_generic"]("col_1") is True
    assert figure_semantics_kwargs["normalize_dataframe_headers"]([" A "]) == ["A"]
    assert figure_semantics_kwargs["normalize_dataframe_matrix"]([[" 1 "]]) == [["1"]]
    assert figure_semantics_kwargs["figure_axis_dimension_label"](["2019", "2020"]) == "dimension"
    assert figure_semantics_kwargs["headers_need_recovery"](["A"]) is False
    assert figure_semantics_kwargs["recover_low_signal_headers"](["A"], [{"row_index": 1}]) == (
        ["A"],
        [{"row_index": 1}],
    )
    assert figure_vision_payload_kwargs["gemini_vision_enable_figures"] is True
    assert figure_vision_payload_kwargs["gemini_vision_max_figures_per_page"] == 4
    assert figure_vision_payload_kwargs["gemini_vision_min_figure_quality"] == 0.65
    assert figure_vision_payload_kwargs["infer_figure_type_from_text"]("sales chart") == "chart"
    assert figure_vision_payload_kwargs["safe_text_list"]([" a ", "", "b"]) == ["a", "b"]
    assert figure_vision_payload_kwargs["normalize_figure_key_values"]([{"name": "x"}]) == [{"name": "x"}]
    assert figure_vision_payload_kwargs["coerce_figure_dataframe"]() == (["A"], [["1"]], "model")
    assert figure_vision_payload_kwargs["recover_figure_title_and_caption"]() == ("Title", "Caption")
    assert figure_vision_payload_kwargs["to_float_or_none"]("0.7") == 0.7
    assert figure_vision_payload_kwargs["count_figure_markers_in_text"]("Figure 1") == 1
    assert visual_figure_builder_kwargs["append_ref"]([], {}, "r1", "text", [1.0, 0.0, 0.0, 1.0, 1.0]) is None
    assert visual_figure_builder_kwargs["layout_bbox_to_ref_bbox"]() == [1.0, 0.0, 0.0, 1.0, 1.0]


def test_parser_visual_payload_bundle_runtime_builds_table_kwargs() -> None:
    runtime = ParserVisualPayloadBundleRuntime()

    vision_table_to_matrix = lambda table: [["A", "B"], ["1", "2"]]
    normalize_text = lambda text: str(text).strip()
    safe_text_list = lambda items, **kwargs: [str(item).strip() for item in (items or []) if str(item).strip()]
    normalize_token_for_compare = lambda text: str(text).lower()
    headers_need_recovery = lambda headers: False
    infer_headers_and_data_rows = lambda rows: (["A", "B"], rows[1:])
    recover_low_signal_headers = lambda headers, rows, **kwargs: (headers, rows)
    drop_redundant_header_like_rows = lambda rows, headers: rows
    decorate_rows_with_meta = lambda rows, headers: rows
    looks_like_false_table = lambda headers, rows: False
    build_header_meta = lambda headers: [{"name": item} for item in headers]
    to_float_or_none = lambda value: float(value) if value is not None else None
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)
    layout_bbox_to_ref_bbox = lambda **kwargs: [2.0, 0.1, 0.2, 0.9, 0.8]
    extract_headers_from_table_payload = lambda payload: ["H1", "H2"]
    extract_rows_from_table_payload = lambda payload: [["1", "2"]]
    matrix_from_html_table = lambda html: [["html", "row"]]

    table_payload_kwargs = runtime.build_table_payload_kwargs(
        table_max_cols=12,
        table_max_rows=80,
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
        normalize_token_for_compare=normalize_token_for_compare,
        headers_need_recovery=headers_need_recovery,
    )
    table_vision_payload_kwargs = runtime.build_table_vision_payload_kwargs(
        gemini_vision_max_tables_per_page=3,
        table_max_rows=80,
        table_max_cols=12,
        ocr_table_min_rows=2,
        vision_table_to_matrix=vision_table_to_matrix,
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
        infer_headers_and_data_rows=infer_headers_and_data_rows,
        recover_low_signal_headers=recover_low_signal_headers,
        drop_redundant_header_like_rows=drop_redundant_header_like_rows,
        decorate_rows_with_meta=decorate_rows_with_meta,
        looks_like_false_table=looks_like_false_table,
        build_header_meta=build_header_meta,
        to_float_or_none=to_float_or_none,
    )
    visual_table_builder_kwargs = runtime.build_visual_table_builder_kwargs(
        visual_use_table_html_fallback=True,
        table_max_cols=12,
        table_max_rows=80,
        table_cell_cap=2000,
        ocr_table_min_rows=2,
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
        to_float_or_none=to_float_or_none,
        append_ref=append_ref,
        layout_bbox_to_ref_bbox=layout_bbox_to_ref_bbox,
        build_header_meta=build_header_meta,
        decorate_rows_with_meta=decorate_rows_with_meta,
        extract_headers_from_table_payload=extract_headers_from_table_payload,
        extract_rows_from_table_payload=extract_rows_from_table_payload,
        matrix_from_html_table=matrix_from_html_table,
        recover_low_signal_headers=recover_low_signal_headers,
        looks_like_false_table=looks_like_false_table,
    )

    assert table_payload_kwargs["table_max_cols"] == 12
    assert table_payload_kwargs["table_max_rows"] == 80
    assert table_payload_kwargs["normalize_text"]("  v  ") == "v"
    assert table_payload_kwargs["safe_text_list"]([" a ", "", "b"]) == ["a", "b"]
    assert table_payload_kwargs["normalize_token_for_compare"]("ABC") == "abc"
    assert table_payload_kwargs["headers_need_recovery"](["A"]) is False
    assert table_vision_payload_kwargs["gemini_vision_max_tables_per_page"] == 3
    assert table_vision_payload_kwargs["ocr_table_min_rows"] == 2
    assert table_vision_payload_kwargs["vision_table_to_matrix"]({"headers": ["A", "B"]}) == [["A", "B"], ["1", "2"]]
    assert table_vision_payload_kwargs["infer_headers_and_data_rows"](
        [{"row_index": 1}, {"row_index": 2}]
    ) == (["A", "B"], [{"row_index": 2}])
    assert table_vision_payload_kwargs["recover_low_signal_headers"](["A"], [{"row_index": 1}]) == (
        ["A"],
        [{"row_index": 1}],
    )
    assert table_vision_payload_kwargs["drop_redundant_header_like_rows"]([], ["A"]) == []
    assert table_vision_payload_kwargs["decorate_rows_with_meta"]([], ["A"]) == []
    assert table_vision_payload_kwargs["looks_like_false_table"](["A"], []) is False
    assert table_vision_payload_kwargs["build_header_meta"](["A"]) == [{"name": "A"}]
    assert table_vision_payload_kwargs["to_float_or_none"]("0.9") == 0.9
    assert visual_table_builder_kwargs["visual_use_table_html_fallback"] is True
    assert visual_table_builder_kwargs["table_cell_cap"] == 2000
    assert visual_table_builder_kwargs["append_ref"]([], {}, "r1", "cell", [1.0, 0.0, 0.0, 1.0, 1.0]) is None
    assert visual_table_builder_kwargs["layout_bbox_to_ref_bbox"]() == [2.0, 0.1, 0.2, 0.9, 0.8]
    assert visual_table_builder_kwargs["extract_headers_from_table_payload"]({}) == ["H1", "H2"]
    assert visual_table_builder_kwargs["extract_rows_from_table_payload"]({}) == [["1", "2"]]
    assert visual_table_builder_kwargs["matrix_from_html_table"]("<table></table>") == [["html", "row"]]


def test_parser_visual_payload_bundle_runtime_builds_visual_signal_kwargs() -> None:
    runtime = ParserVisualPayloadBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    looks_like_table_cue_text = lambda text: "table" in str(text).lower()
    looks_like_figure_cue_text = lambda text: "figure" in str(text).lower()
    contains_figure_marker = lambda text: "fig" in str(text).lower()

    table_cue_kwargs = runtime.build_visual_table_cue_kwargs(
        ocr_cue_max_pages=180,
        visual_weak_table_min=3,
        visual_weak_table_quality=0.48,
        normalize_text=normalize_text,
    )
    page_signal_kwargs = runtime.build_visual_page_signal_kwargs(
        gemini_vision_max_pages=12,
        gemini_vision_min_table_quality=0.63,
        gemini_vision_enable_figures=True,
        looks_like_table_cue_text=looks_like_table_cue_text,
        looks_like_figure_cue_text=looks_like_figure_cue_text,
        contains_figure_marker=contains_figure_marker,
    )

    assert table_cue_kwargs == {
        "ocr_cue_max_pages": 180,
        "visual_weak_table_min": 3,
        "visual_weak_table_quality": 0.48,
        "normalize_text": normalize_text,
    }
    assert page_signal_kwargs["gemini_vision_max_pages"] == 12
    assert page_signal_kwargs["gemini_vision_min_table_quality"] == 0.63
    assert page_signal_kwargs["gemini_vision_enable_figures"] is True
    assert page_signal_kwargs["looks_like_table_cue_text"]("table 1") is True
    assert page_signal_kwargs["looks_like_figure_cue_text"]("figure 2") is True
    assert page_signal_kwargs["contains_figure_marker"]("fig 3") is True
