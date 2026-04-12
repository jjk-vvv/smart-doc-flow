from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_document_table_bootstrap_module = import_module("module2.app.core.parsers.parser_document_table_bootstrap_runtime")

ParserDocumentTableBootstrapRuntime = parser_document_table_bootstrap_module.ParserDocumentTableBootstrapRuntime


def test_parser_document_table_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserDocumentTableBootstrapRuntime()

    attrs = runtime.build_document_table_runtime_attrs(
        normalize_text=lambda text: str(text).strip(),
        normalize_token_for_compare=lambda text: str(text).lower(),
        runtime_page_count_provider=lambda: 6,
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
        table_max_rows=120,
        table_max_cols=20,
        xlsx_sheet_limit=8,
        xlsx_cell_cap=1600,
        table_merge_max_page_gap=1,
        table_merge_header_sim=0.58,
        table_merge_col_overlap=0.55,
        table_cell_cap=3000,
        table_merge_enable=True,
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
        ocr_table_min_rows=2,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        looks_like_table_cue_text=lambda text: "table" in str(text).lower(),
    )

    expected_keys = {
        "_table_header",
        "_nonpdf_table_runtime",
        "_nonpdf_table_rows_runtime",
        "_nonpdf_text_runtime",
        "_docx_parse_runtime",
        "_xlsx_runtime",
        "_xlsx_table_runtime",
        "_xlsx_parse_runtime",
        "_table_merge_runtime",
        "_pdf_fitz_table_runtime",
        "_ocr_table_utils",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_table_header"], "infer_headers_and_data_rows")
    assert hasattr(attrs["_nonpdf_table_runtime"], "build_table_block")
    assert hasattr(attrs["_nonpdf_table_rows_runtime"], "build_rows_payload")
    assert hasattr(attrs["_nonpdf_text_runtime"], "append_text_ref")
    assert hasattr(attrs["_docx_parse_runtime"], "consume_document")
    assert hasattr(attrs["_xlsx_runtime"], "shared_strings_from_zip")
    assert hasattr(attrs["_xlsx_table_runtime"], "consume_openpyxl_workbook")
    assert hasattr(attrs["_xlsx_parse_runtime"], "parse_xlsx")
    assert hasattr(attrs["_table_merge_runtime"], "merge_same_page_tables")
    assert hasattr(attrs["_pdf_fitz_table_runtime"], "extract_pdf_tables_with_fitz")
    assert hasattr(attrs["_ocr_table_utils"], "looks_like_false_table")
