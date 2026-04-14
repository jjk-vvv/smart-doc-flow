from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_document_table_bootstrap_runtime_module = import_module("app.modules.module2.core.parsers.parser_document_table_bootstrap_runtime")

ParserDocumentTableBootstrapRuntime = (
    parser_document_table_bootstrap_runtime_module.ParserDocumentTableBootstrapRuntime
)


def test_parser_table_helper_bundle_runtime_builds_table_merge_and_pdf_fitz_kwargs() -> None:
    runtime = ParserDocumentTableBootstrapRuntime()

    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()
    is_page_number_token = lambda text: str(text).isdigit()
    drop_redundant_header_like_rows = lambda rows, headers: rows
    decorate_rows_with_meta = lambda rows, headers: rows
    build_header_meta = lambda headers: [{"name": item} for item in headers]
    merge_same_page_tables = lambda tables: tables
    merge_cross_page_tables = lambda tables: tables

    table_merge_kwargs = runtime.build_table_merge_kwargs(
        table_merge_max_page_gap=1,
        table_merge_header_sim=0.58,
        table_merge_col_overlap=0.55,
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        is_page_number_token=is_page_number_token,
        drop_redundant_header_like_rows=drop_redundant_header_like_rows,
    )
    pdf_fitz_kwargs = runtime.build_pdf_fitz_table_kwargs(
        table_max_rows=120,
        table_max_cols=20,
        table_cell_cap=3000,
        table_merge_enable=True,
        normalize_text=normalize_text,
        decorate_rows_with_meta=decorate_rows_with_meta,
        build_header_meta=build_header_meta,
        merge_same_page_tables=merge_same_page_tables,
        merge_cross_page_tables=merge_cross_page_tables,
    )

    assert table_merge_kwargs["table_merge_max_page_gap"] == 1
    assert table_merge_kwargs["table_merge_header_sim"] == 0.58
    assert table_merge_kwargs["table_merge_col_overlap"] == 0.55
    assert table_merge_kwargs["normalize_text"]("  value ") == "value"
    assert table_merge_kwargs["normalize_token_for_compare"]("ABC") == "abc"
    assert table_merge_kwargs["is_page_number_token"]("12") is True
    assert table_merge_kwargs["drop_redundant_header_like_rows"]([], []) == []
    assert pdf_fitz_kwargs["table_max_rows"] == 120
    assert pdf_fitz_kwargs["table_max_cols"] == 20
    assert pdf_fitz_kwargs["table_cell_cap"] == 3000
    assert pdf_fitz_kwargs["table_merge_enable"] is True
    assert pdf_fitz_kwargs["decorate_rows_with_meta"]([], []) == []
    assert pdf_fitz_kwargs["build_header_meta"](["A"]) == [{"name": "A"}]
    assert pdf_fitz_kwargs["merge_same_page_tables"]([]) == []
    assert pdf_fitz_kwargs["merge_cross_page_tables"]([]) == []


def test_parser_table_helper_bundle_runtime_builds_ocr_table_utils_kwargs() -> None:
    runtime = ParserDocumentTableBootstrapRuntime()

    looks_like_table_cue_text = lambda text: "table" in str(text).lower()
    merge_same_page_tables = lambda tables: [{"merged": "same", "tables": tables}]
    merge_cross_page_tables = lambda tables: [{"merged": "cross", "tables": tables}]

    kwargs = runtime.build_ocr_table_utils_kwargs(
        ocr_max_pages=4,
        ocr_front_scan_pages=72,
        ocr_extra_sample_pages=10,
        ocr_cue_neighbor=1,
        ocr_cue_max_pages=220,
        ocr_max_scan_pages=96,
        ocr_cue_boost_max_pages=110,
        ocr_min_coverage_ratio=0.14,
        ocr_min_scan_pages=28,
        visual_weak_table_min=4,
        ocr_table_min_quality=0.52,
        ocr_line_aug_max_extra_cue_pages=24,
        ocr_uncovered_line_aug_pages=8,
        table_merge_enable=True,
        ocr_table_min_rows=2,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        looks_like_table_cue_text=looks_like_table_cue_text,
        merge_same_page_tables=merge_same_page_tables,
        merge_cross_page_tables=merge_cross_page_tables,
    )

    assert kwargs["ocr_max_pages"] == 4
    assert kwargs["ocr_front_scan_pages"] == 72
    assert kwargs["ocr_extra_sample_pages"] == 10
    assert kwargs["ocr_cue_neighbor"] == 1
    assert kwargs["ocr_cue_max_pages"] == 220
    assert kwargs["ocr_max_scan_pages"] == 96
    assert kwargs["ocr_cue_boost_max_pages"] == 110
    assert kwargs["ocr_min_coverage_ratio"] == 0.14
    assert kwargs["ocr_min_scan_pages"] == 28
    assert kwargs["visual_weak_table_min"] == 4
    assert kwargs["ocr_table_min_quality"] == 0.52
    assert kwargs["ocr_line_aug_max_extra_cue_pages"] == 24
    assert kwargs["ocr_uncovered_line_aug_pages"] == 8
    assert kwargs["table_merge_enable"] is True
    assert kwargs["ocr_table_min_rows"] == 2
    assert kwargs["ocr_table_row_gap"] == 0.08
    assert kwargs["ocr_table_col_tol"] == 0.04
    assert kwargs["looks_like_table_cue_text"]("table 1") is True
    assert kwargs["merge_same_page_tables"]([{"id": 1}]) == [{"merged": "same", "tables": [{"id": 1}]}]
    assert kwargs["merge_cross_page_tables"]([{"id": 2}]) == [{"merged": "cross", "tables": [{"id": 2}]}]
