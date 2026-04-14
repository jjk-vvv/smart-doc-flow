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


def test_parser_document_table_bundle_runtime_builds_nonpdf_component_kwargs() -> None:
    runtime = ParserDocumentTableBootstrapRuntime()

    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()
    contains_figure_marker = lambda text: "figure" in str(text).lower()
    contains_catalog_marker = lambda text: "catalog" in str(text).lower()
    runtime_page_count_provider = lambda: 12

    table_header_kwargs = runtime.build_table_header_kwargs(
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        contains_figure_marker=contains_figure_marker,
        contains_catalog_marker=contains_catalog_marker,
        runtime_page_count_provider=runtime_page_count_provider,
    )
    nonpdf_table_kwargs = runtime.build_nonpdf_table_kwargs(
        infer_headers_and_data_rows=lambda rows: (["h1"], rows),
        drop_redundant_header_like_rows=lambda rows, headers: rows,
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
    )
    nonpdf_table_rows_kwargs = runtime.build_nonpdf_table_rows_kwargs(
        normalize_text=normalize_text,
    )
    nonpdf_text_kwargs = runtime.build_nonpdf_text_kwargs(
        normalize_text=normalize_text,
    )

    assert table_header_kwargs["normalize_text"]("  x  ") == "x"
    assert table_header_kwargs["normalize_token_for_compare"]("HeLLo") == "hello"
    assert table_header_kwargs["contains_figure_marker"]("figure 1") is True
    assert table_header_kwargs["contains_catalog_marker"]("catalog") is True
    assert table_header_kwargs["runtime_page_count_provider"]() == 12
    assert nonpdf_table_kwargs["build_header_meta"](["A"]) == [{"name": "A"}]
    assert nonpdf_table_rows_kwargs["normalize_text"]("  row  ") == "row"
    assert nonpdf_text_kwargs["normalize_text"]("  text  ") == "text"


def test_parser_document_table_bundle_runtime_builds_docx_and_xlsx_kwargs() -> None:
    runtime = ParserDocumentTableBootstrapRuntime()

    normalize_text = lambda text: str(text).strip()
    xlsx_runtime = object()
    build_indexed_rows_payload = lambda *args, **kwargs: ([], 0, False)
    build_table_block = lambda *args, **kwargs: {"table_id": "t1"}
    consume_openpyxl_workbook = lambda *args, **kwargs: ([], 0)
    consume_zip_workbook = lambda *args, **kwargs: ([], 0, 0)
    append_xlsx_sheet_placeholders = lambda *args, **kwargs: 3
    append_text_ref = lambda *args, **kwargs: True

    docx_kwargs = runtime.build_docx_parse_kwargs(
        table_max_rows=120,
        table_max_cols=20,
        normalize_text=normalize_text,
        append_numbered_text_ref=lambda *args, **kwargs: 2,
        build_rows_payload=lambda *args, **kwargs: [],
        build_table_block=build_table_block,
    )
    xlsx_runtime_kwargs = runtime.build_xlsx_runtime_kwargs(
        normalize_text=normalize_text,
        sheet_limit=8,
    )
    xlsx_table_kwargs = runtime.build_xlsx_table_kwargs(
        sheet_limit=8,
        table_max_rows=120,
        table_max_cols=20,
        xlsx_cell_cap=1600,
        xlsx_runtime=xlsx_runtime,
        build_indexed_rows_payload=build_indexed_rows_payload,
        build_table_block=build_table_block,
    )
    xlsx_parse_kwargs = runtime.build_xlsx_parse_kwargs(
        sheet_limit=8,
        consume_openpyxl_workbook=consume_openpyxl_workbook,
        consume_zip_workbook=consume_zip_workbook,
        append_xlsx_sheet_placeholders=append_xlsx_sheet_placeholders,
        append_text_ref=append_text_ref,
    )

    assert docx_kwargs["table_max_rows"] == 120
    assert docx_kwargs["table_max_cols"] == 20
    assert docx_kwargs["normalize_text"]("  docx  ") == "docx"
    assert xlsx_runtime_kwargs == {
        "normalize_text": normalize_text,
        "sheet_limit": 8,
    }
    assert xlsx_table_kwargs["xlsx_runtime"] is xlsx_runtime
    assert xlsx_table_kwargs["build_indexed_rows_payload"] is build_indexed_rows_payload
    assert xlsx_parse_kwargs["consume_openpyxl_workbook"] is consume_openpyxl_workbook
    assert xlsx_parse_kwargs["consume_zip_workbook"] is consume_zip_workbook
    assert xlsx_parse_kwargs["append_xlsx_sheet_placeholders"] is append_xlsx_sheet_placeholders
    assert xlsx_parse_kwargs["append_text_ref"] is append_text_ref
