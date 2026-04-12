from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_ocr_table_inference_bundle_runtime_module = import_module("module2.app.core.parsers.parser_semantic_bootstrap_runtime")

ParserOcrTableInferenceBundleRuntime = (
    parser_ocr_table_inference_bundle_runtime_module.ParserOcrTableInferenceBundleRuntime
)


def test_parser_ocr_table_inference_bundle_runtime_builds_threshold_kwargs() -> None:
    runtime = ParserOcrTableInferenceBundleRuntime()

    kwargs = runtime.build_threshold_kwargs(
        ocr_table_min_quality=0.52,
        ocr_table_min_cols=2,
        ocr_table_min_rows=2,
        ocr_table_row_tol=0.018,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        ocr_table_relaxed_row_gap_scale=1.5,
        ocr_table_relaxed_align_min=0.36,
        ocr_table_relaxed_overlap_min=0.3,
        ocr_table_relaxed_col_diff_max=2,
        table_max_rows=120,
        table_max_cols=20,
        table_cell_cap=3000,
        table_merge_enable=True,
    )

    assert kwargs == {
        "ocr_table_min_quality": 0.52,
        "ocr_table_min_cols": 2,
        "ocr_table_min_rows": 2,
        "ocr_table_row_tol": 0.018,
        "ocr_table_row_gap": 0.08,
        "ocr_table_col_tol": 0.04,
        "ocr_table_relaxed_row_gap_scale": 1.5,
        "ocr_table_relaxed_align_min": 0.36,
        "ocr_table_relaxed_overlap_min": 0.3,
        "ocr_table_relaxed_col_diff_max": 2,
        "table_max_rows": 120,
        "table_max_cols": 20,
        "table_cell_cap": 3000,
        "table_merge_enable": True,
    }


def test_parser_ocr_table_inference_bundle_runtime_builds_callback_kwargs() -> None:
    runtime = ParserOcrTableInferenceBundleRuntime()

    runtime_page_count_provider = lambda: 8
    infer_headers_and_data_rows = lambda rows: (["A"], rows)
    drop_redundant_header_like_rows = lambda rows, headers: rows
    decorate_rows_with_meta = lambda rows, headers: rows
    build_header_meta = lambda headers: [{"name": item} for item in headers]
    looks_like_false_table = lambda headers, rows: False
    normalize_text = lambda text: str(text).strip()
    contains_section_marker = lambda text: "section" in str(text).lower()
    is_page_number_token = lambda text: str(text).isdigit()
    dedupe_ocr_cells = lambda cells: cells
    median_cell_height = lambda cells: 12.0
    cluster_ocr_rows = lambda cells, tol: [{"cells": cells, "tol": tol}]
    group_table_rows = lambda rows, min_cols, row_gap=None: [rows]
    split_group_by_row_gaps = lambda group: [group]
    build_col_anchors = lambda rows, tol: [0.1, 0.5]
    nearest_anchor_index = lambda x, anchors: 0
    expand_group_with_sparse_rows = lambda group, anchors, all_rows: group
    table_quality_score = lambda group, anchors: 0.9
    split_table_line = lambda line: [line]
    is_table_line = lambda line, tokens: True
    merge_same_page_tables = lambda tables: tables
    merge_cross_page_tables = lambda tables: tables

    kwargs = runtime.build_callback_kwargs(
        runtime_page_count_provider=runtime_page_count_provider,
        infer_headers_and_data_rows=infer_headers_and_data_rows,
        drop_redundant_header_like_rows=drop_redundant_header_like_rows,
        decorate_rows_with_meta=decorate_rows_with_meta,
        build_header_meta=build_header_meta,
        looks_like_false_table=looks_like_false_table,
        normalize_text=normalize_text,
        contains_section_marker=contains_section_marker,
        is_page_number_token=is_page_number_token,
        dedupe_ocr_cells=dedupe_ocr_cells,
        median_cell_height=median_cell_height,
        cluster_ocr_rows=cluster_ocr_rows,
        group_table_rows=group_table_rows,
        split_group_by_row_gaps=split_group_by_row_gaps,
        build_col_anchors=build_col_anchors,
        nearest_anchor_index=nearest_anchor_index,
        expand_group_with_sparse_rows=expand_group_with_sparse_rows,
        table_quality_score=table_quality_score,
        split_table_line=split_table_line,
        is_table_line=is_table_line,
        merge_same_page_tables=merge_same_page_tables,
        merge_cross_page_tables=merge_cross_page_tables,
    )

    assert kwargs["runtime_page_count_provider"]() == 8
    assert kwargs["infer_headers_and_data_rows"]([{"cells": []}]) == (["A"], [{"cells": []}])
    assert kwargs["drop_redundant_header_like_rows"]([], ["A"]) == []
    assert kwargs["decorate_rows_with_meta"]([], ["A"]) == []
    assert kwargs["build_header_meta"](["A"]) == [{"name": "A"}]
    assert kwargs["looks_like_false_table"](["A"], []) is False
    assert kwargs["normalize_text"]("  x  ") == "x"
    assert kwargs["contains_section_marker"]("section 1") is True
    assert kwargs["is_page_number_token"]("12") is True
    assert kwargs["dedupe_ocr_cells"]([{"text": "1"}]) == [{"text": "1"}]
    assert kwargs["median_cell_height"]([{"h": 12}]) == 12.0
    assert kwargs["cluster_ocr_rows"]([{"text": "1"}], 0.2) == [{"cells": [{"text": "1"}], "tol": 0.2}]
    assert kwargs["group_table_rows"]([{"cells": []}], 2) == [[{"cells": []}]]
    assert kwargs["split_group_by_row_gaps"]([{"cells": []}]) == [[{"cells": []}]]
    assert kwargs["build_col_anchors"]([{"cells": []}], 0.04) == [0.1, 0.5]
    assert kwargs["nearest_anchor_index"](0.2, [0.1, 0.5]) == 0
    assert kwargs["expand_group_with_sparse_rows"]([], [], []) == []
    assert kwargs["table_quality_score"]([], []) == 0.9
    assert kwargs["split_table_line"]("A B") == ["A B"]
    assert kwargs["is_table_line"]("A B", ["A", "B"]) is True
    assert kwargs["merge_same_page_tables"]([{"id": 1}]) == [{"id": 1}]
    assert kwargs["merge_cross_page_tables"]([{"id": 2}]) == [{"id": 2}]
