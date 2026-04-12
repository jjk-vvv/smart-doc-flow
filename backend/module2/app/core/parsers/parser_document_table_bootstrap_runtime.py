from __future__ import annotations

from typing import Any, Callable, Dict

from ..format.docx_document_runtime import DocxParseRuntime
from ..format.nonpdf_content_runtime import NonPdfTableRowsRuntime, NonPdfTableRuntime, NonPdfTextRuntime
from ..table.ocr_table_utils import OcrTableUtils
from ..pdf.pdf_fitz_table_runtime import PdfFitzTableRuntime
from ..table.table_header_runtime import TableHeaderRuntime
from ..table.table_merge_runtime import TableMergeRuntime
from ..format.xlsx_runtime import XlsxParseRuntime, XlsxRuntime, XlsxTableRuntime


RuntimeCallback = Callable[..., Any]


class ParserDocumentTableBootstrapRuntime:
    """Own both table kwarg assembly and runtime construction for parser table components."""

    @staticmethod
    def _default_infer_headers_and_data_rows(rows_payload: Any) -> Any:
        rows = rows_payload if isinstance(rows_payload, list) else []
        if not rows:
            return [], []
        first_row = rows[0] if isinstance(rows[0], dict) else {}
        cells = first_row.get("cells", []) if isinstance(first_row, dict) else []
        header_pairs = []
        for cell in cells if isinstance(cells, list) else []:
            if not isinstance(cell, dict):
                continue
            try:
                col_index = int(cell.get("col_index", 0) or 0)
            except (TypeError, ValueError):
                col_index = 0
            if col_index <= 0:
                continue
            header_pairs.append((col_index, str(cell.get("text", "") or "").strip() or f"col_{col_index}"))
        header_pairs.sort(key=lambda item: item[0])
        headers = [text for _, text in header_pairs]
        data_rows = []
        for row_index, row in enumerate(rows[1:], start=1):
            if not isinstance(row, dict):
                continue
            cells = row.get("cells", [])
            if not isinstance(cells, list):
                continue
            data_rows.append(
                {
                    "row_index": row_index,
                    "cells": [dict(cell) for cell in cells if isinstance(cell, dict)],
                }
            )
        return headers, data_rows

    @staticmethod
    def _default_drop_redundant_header_like_rows(rows_payload: Any, _headers: Any) -> Any:
        return rows_payload if isinstance(rows_payload, list) else []

    def build_table_header_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        contains_figure_marker: RuntimeCallback,
        contains_catalog_marker: RuntimeCallback,
        runtime_page_count_provider: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "normalize_token_for_compare": normalize_token_for_compare,
            "contains_figure_marker": contains_figure_marker,
            "contains_catalog_marker": contains_catalog_marker,
            "runtime_page_count_provider": runtime_page_count_provider,
        }

    def build_nonpdf_table_kwargs(
        self,
        *,
        infer_headers_and_data_rows: RuntimeCallback,
        drop_redundant_header_like_rows: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        build_header_meta: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "infer_headers_and_data_rows": infer_headers_and_data_rows,
            "drop_redundant_header_like_rows": drop_redundant_header_like_rows,
            "decorate_rows_with_meta": decorate_rows_with_meta,
            "build_header_meta": build_header_meta,
        }

    def build_nonpdf_table_rows_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
        }

    def build_nonpdf_text_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
        }

    def build_docx_parse_kwargs(
        self,
        *,
        table_max_rows: int,
        table_max_cols: int,
        normalize_text: RuntimeCallback,
        append_numbered_text_ref: RuntimeCallback,
        build_rows_payload: RuntimeCallback,
        build_table_block: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_max_rows": table_max_rows,
            "table_max_cols": table_max_cols,
            "normalize_text": normalize_text,
            "append_numbered_text_ref": append_numbered_text_ref,
            "build_rows_payload": build_rows_payload,
            "build_table_block": build_table_block,
        }

    def build_xlsx_runtime_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        sheet_limit: int,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "sheet_limit": sheet_limit,
        }

    def build_xlsx_table_kwargs(
        self,
        *,
        sheet_limit: int,
        table_max_rows: int,
        table_max_cols: int,
        xlsx_cell_cap: int,
        xlsx_runtime: Any,
        build_indexed_rows_payload: RuntimeCallback,
        build_table_block: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "sheet_limit": sheet_limit,
            "table_max_rows": table_max_rows,
            "table_max_cols": table_max_cols,
            "xlsx_cell_cap": xlsx_cell_cap,
            "xlsx_runtime": xlsx_runtime,
            "build_indexed_rows_payload": build_indexed_rows_payload,
            "build_table_block": build_table_block,
        }

    def build_xlsx_parse_kwargs(
        self,
        *,
        sheet_limit: int,
        consume_openpyxl_workbook: RuntimeCallback,
        consume_zip_workbook: RuntimeCallback,
        append_xlsx_sheet_placeholders: RuntimeCallback,
        append_text_ref: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "sheet_limit": sheet_limit,
            "consume_openpyxl_workbook": consume_openpyxl_workbook,
            "consume_zip_workbook": consume_zip_workbook,
            "append_xlsx_sheet_placeholders": append_xlsx_sheet_placeholders,
            "append_text_ref": append_text_ref,
        }

    def build_table_merge_kwargs(
        self,
        *,
        table_merge_max_page_gap: int,
        table_merge_header_sim: float,
        table_merge_col_overlap: float,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        is_page_number_token: RuntimeCallback,
        drop_redundant_header_like_rows: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_merge_max_page_gap": table_merge_max_page_gap,
            "table_merge_header_sim": table_merge_header_sim,
            "table_merge_col_overlap": table_merge_col_overlap,
            "normalize_text": normalize_text,
            "normalize_token_for_compare": normalize_token_for_compare,
            "is_page_number_token": is_page_number_token,
            "drop_redundant_header_like_rows": drop_redundant_header_like_rows,
        }

    def build_pdf_fitz_table_kwargs(
        self,
        *,
        table_max_rows: int,
        table_max_cols: int,
        table_cell_cap: int,
        table_merge_enable: bool,
        normalize_text: RuntimeCallback,
        infer_headers_and_data_rows: RuntimeCallback | None = None,
        drop_redundant_header_like_rows: RuntimeCallback | None = None,
        decorate_rows_with_meta: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_max_rows": table_max_rows,
            "table_max_cols": table_max_cols,
            "table_cell_cap": table_cell_cap,
            "table_merge_enable": table_merge_enable,
            "normalize_text": normalize_text,
            "infer_headers_and_data_rows": (
                infer_headers_and_data_rows
                if callable(infer_headers_and_data_rows)
                else self._default_infer_headers_and_data_rows
            ),
            "drop_redundant_header_like_rows": (
                drop_redundant_header_like_rows
                if callable(drop_redundant_header_like_rows)
                else self._default_drop_redundant_header_like_rows
            ),
            "decorate_rows_with_meta": decorate_rows_with_meta,
            "build_header_meta": build_header_meta,
            "merge_same_page_tables": merge_same_page_tables,
            "merge_cross_page_tables": merge_cross_page_tables,
        }

    def build_ocr_table_utils_kwargs(
        self,
        *,
        ocr_max_pages: int,
        ocr_front_scan_pages: int,
        ocr_extra_sample_pages: int,
        ocr_cue_neighbor: int,
        ocr_cue_max_pages: int,
        ocr_max_scan_pages: int,
        ocr_cue_boost_max_pages: int,
        ocr_min_coverage_ratio: float,
        ocr_min_scan_pages: int,
        visual_weak_table_min: int,
        ocr_table_min_quality: float,
        ocr_line_aug_max_extra_cue_pages: int,
        ocr_uncovered_line_aug_pages: int,
        table_merge_enable: bool,
        ocr_table_min_rows: int,
        ocr_table_row_gap: float,
        ocr_table_col_tol: float,
        looks_like_table_cue_text: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "ocr_max_pages": ocr_max_pages,
            "ocr_front_scan_pages": ocr_front_scan_pages,
            "ocr_extra_sample_pages": ocr_extra_sample_pages,
            "ocr_cue_neighbor": ocr_cue_neighbor,
            "ocr_cue_max_pages": ocr_cue_max_pages,
            "ocr_max_scan_pages": ocr_max_scan_pages,
            "ocr_cue_boost_max_pages": ocr_cue_boost_max_pages,
            "ocr_min_coverage_ratio": ocr_min_coverage_ratio,
            "ocr_min_scan_pages": ocr_min_scan_pages,
            "visual_weak_table_min": visual_weak_table_min,
            "ocr_table_min_quality": ocr_table_min_quality,
            "ocr_line_aug_max_extra_cue_pages": ocr_line_aug_max_extra_cue_pages,
            "ocr_uncovered_line_aug_pages": ocr_uncovered_line_aug_pages,
            "table_merge_enable": table_merge_enable,
            "ocr_table_min_rows": ocr_table_min_rows,
            "ocr_table_row_gap": ocr_table_row_gap,
            "ocr_table_col_tol": ocr_table_col_tol,
            "looks_like_table_cue_text": looks_like_table_cue_text,
            "merge_same_page_tables": merge_same_page_tables,
            "merge_cross_page_tables": merge_cross_page_tables,
        }

    def build_document_table_runtime_attrs(
        self,
        *,
        normalize_text: Callable[[str], str],
        normalize_token_for_compare: Callable[[str], str],
        runtime_page_count_provider: Callable[[], int],
        decorate_rows_with_meta: Callable[..., Any],
        build_header_meta: Callable[..., Any],
        table_max_rows: int,
        table_max_cols: int,
        xlsx_sheet_limit: int,
        xlsx_cell_cap: int,
        table_merge_max_page_gap: int,
        table_merge_header_sim: float,
        table_merge_col_overlap: float,
        table_cell_cap: int,
        table_merge_enable: bool,
        ocr_max_pages: int,
        ocr_front_scan_pages: int,
        ocr_extra_sample_pages: int,
        ocr_cue_neighbor: int,
        ocr_cue_max_pages: int,
        ocr_max_scan_pages: int,
        ocr_cue_boost_max_pages: int,
        ocr_min_coverage_ratio: float,
        ocr_min_scan_pages: int,
        visual_weak_table_min: int,
        ocr_table_min_quality: float,
        ocr_line_aug_max_extra_cue_pages: int,
        ocr_uncovered_line_aug_pages: int,
        ocr_table_min_rows: int,
        ocr_table_row_gap: float,
        ocr_table_col_tol: float,
        looks_like_table_cue_text: Callable[..., bool],
    ) -> Dict[str, Any]:
        table_header = TableHeaderRuntime(
            **self.build_table_header_kwargs(
                normalize_text=normalize_text,
                normalize_token_for_compare=normalize_token_for_compare,
                contains_figure_marker=OcrTableUtils.contains_figure_marker,
                contains_catalog_marker=OcrTableUtils.contains_catalog_marker,
                runtime_page_count_provider=runtime_page_count_provider,
            )
        )
        nonpdf_table_runtime = NonPdfTableRuntime(
            **self.build_nonpdf_table_kwargs(
                infer_headers_and_data_rows=table_header.infer_headers_and_data_rows,
                drop_redundant_header_like_rows=table_header.drop_redundant_header_like_rows,
                decorate_rows_with_meta=decorate_rows_with_meta,
                build_header_meta=build_header_meta,
            )
        )
        nonpdf_table_rows_runtime = NonPdfTableRowsRuntime(
            **self.build_nonpdf_table_rows_kwargs(
                normalize_text=normalize_text,
            )
        )
        nonpdf_text_runtime = NonPdfTextRuntime(
            **self.build_nonpdf_text_kwargs(
                normalize_text=normalize_text,
            )
        )
        docx_parse_runtime = DocxParseRuntime(
            **self.build_docx_parse_kwargs(
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                normalize_text=normalize_text,
                append_numbered_text_ref=nonpdf_text_runtime.append_numbered_text_ref,
                build_rows_payload=nonpdf_table_rows_runtime.build_rows_payload,
                build_table_block=nonpdf_table_runtime.build_table_block,
            )
        )
        xlsx_runtime = XlsxRuntime(
            **self.build_xlsx_runtime_kwargs(
                normalize_text=normalize_text,
                sheet_limit=xlsx_sheet_limit,
            )
        )
        xlsx_table_runtime = XlsxTableRuntime(
            **self.build_xlsx_table_kwargs(
                sheet_limit=xlsx_sheet_limit,
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                xlsx_cell_cap=xlsx_cell_cap,
                xlsx_runtime=xlsx_runtime,
                build_indexed_rows_payload=nonpdf_table_rows_runtime.build_indexed_rows_payload,
                build_table_block=nonpdf_table_runtime.build_table_block,
            )
        )
        xlsx_parse_runtime = XlsxParseRuntime(
            **self.build_xlsx_parse_kwargs(
                sheet_limit=xlsx_sheet_limit,
                consume_openpyxl_workbook=xlsx_table_runtime.consume_openpyxl_workbook,
                consume_zip_workbook=xlsx_table_runtime.consume_zip_workbook,
                append_xlsx_sheet_placeholders=nonpdf_text_runtime.append_xlsx_sheet_placeholders,
                append_text_ref=nonpdf_text_runtime.append_text_ref,
            )
        )
        table_merge_runtime = TableMergeRuntime(
            **self.build_table_merge_kwargs(
                table_merge_max_page_gap=table_merge_max_page_gap,
                table_merge_header_sim=table_merge_header_sim,
                table_merge_col_overlap=table_merge_col_overlap,
                normalize_text=normalize_text,
                normalize_token_for_compare=normalize_token_for_compare,
                is_page_number_token=OcrTableUtils.is_page_number_token,
                drop_redundant_header_like_rows=table_header.drop_redundant_header_like_rows,
            )
        )
        pdf_fitz_table_runtime = PdfFitzTableRuntime(
            **self.build_pdf_fitz_table_kwargs(
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                table_cell_cap=table_cell_cap,
                table_merge_enable=table_merge_enable,
                normalize_text=normalize_text,
                infer_headers_and_data_rows=table_header.infer_headers_and_data_rows,
                drop_redundant_header_like_rows=table_header.drop_redundant_header_like_rows,
                decorate_rows_with_meta=decorate_rows_with_meta,
                build_header_meta=build_header_meta,
                merge_same_page_tables=table_merge_runtime.merge_same_page_tables,
                merge_cross_page_tables=table_merge_runtime.merge_cross_page_tables,
            )
        )
        ocr_table_utils = OcrTableUtils(
            **self.build_ocr_table_utils_kwargs(
                ocr_max_pages=ocr_max_pages,
                ocr_front_scan_pages=ocr_front_scan_pages,
                ocr_extra_sample_pages=ocr_extra_sample_pages,
                ocr_cue_neighbor=ocr_cue_neighbor,
                ocr_cue_max_pages=ocr_cue_max_pages,
                ocr_max_scan_pages=ocr_max_scan_pages,
                ocr_cue_boost_max_pages=ocr_cue_boost_max_pages,
                ocr_min_coverage_ratio=ocr_min_coverage_ratio,
                ocr_min_scan_pages=ocr_min_scan_pages,
                visual_weak_table_min=visual_weak_table_min,
                ocr_table_min_quality=ocr_table_min_quality,
                ocr_line_aug_max_extra_cue_pages=ocr_line_aug_max_extra_cue_pages,
                ocr_uncovered_line_aug_pages=ocr_uncovered_line_aug_pages,
                table_merge_enable=table_merge_enable,
                ocr_table_min_rows=ocr_table_min_rows,
                ocr_table_row_gap=ocr_table_row_gap,
                ocr_table_col_tol=ocr_table_col_tol,
                looks_like_table_cue_text=looks_like_table_cue_text,
                merge_same_page_tables=table_merge_runtime.merge_same_page_tables,
                merge_cross_page_tables=table_merge_runtime.merge_cross_page_tables,
            )
        )
        return {
            "_table_header": table_header,
            "_nonpdf_table_runtime": nonpdf_table_runtime,
            "_nonpdf_table_rows_runtime": nonpdf_table_rows_runtime,
            "_nonpdf_text_runtime": nonpdf_text_runtime,
            "_docx_parse_runtime": docx_parse_runtime,
            "_xlsx_runtime": xlsx_runtime,
            "_xlsx_table_runtime": xlsx_table_runtime,
            "_xlsx_parse_runtime": xlsx_parse_runtime,
            "_table_merge_runtime": table_merge_runtime,
            "_pdf_fitz_table_runtime": pdf_fitz_table_runtime,
            "_ocr_table_utils": ocr_table_utils,
        }
