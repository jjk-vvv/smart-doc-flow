from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
VisionTableToMatrix = Callable[[Any], List[List[str]]]
NormalizeText = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
InferHeadersAndDataRows = Callable[[List[Dict[str, Any]]], Tuple[List[str], List[Dict[str, Any]]]]
RecoverLowSignalHeaders = Callable[..., Tuple[List[str], List[Dict[str, Any]]]]
DropRedundantHeaderLikeRows = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
DecorateRowsWithMeta = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
LooksLikeFalseTable = Callable[[List[str], List[Dict[str, Any]]], bool]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
ToFloatOrNone = Callable[[Any], Optional[float]]


class TableVisionPayloadRuntime:
    """Build table blocks from vision payloads while keeping parser signatures stable."""

    def __init__(
        self,
        *,
        vision_max_tables_per_page: int,
        table_max_rows: int,
        table_max_cols: int,
        ocr_table_min_rows: int,
        vision_table_to_matrix: VisionTableToMatrix,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        infer_headers_and_data_rows: InferHeadersAndDataRows,
        recover_low_signal_headers: RecoverLowSignalHeaders,
        drop_redundant_header_like_rows: DropRedundantHeaderLikeRows,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        looks_like_false_table: LooksLikeFalseTable,
        build_header_meta: BuildHeaderMeta,
        to_float_or_none: ToFloatOrNone,
    ) -> None:
        self.vision_max_tables_per_page = max(0, int(vision_max_tables_per_page or 0))
        self.table_max_rows = max(1, int(table_max_rows or 1))
        self.table_max_cols = max(1, int(table_max_cols or 1))
        self.ocr_table_min_rows = max(1, int(ocr_table_min_rows or 1))
        self._vision_table_to_matrix = vision_table_to_matrix
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._infer_headers_and_data_rows = infer_headers_and_data_rows
        self._recover_low_signal_headers = recover_low_signal_headers
        self._drop_redundant_header_like_rows = drop_redundant_header_like_rows
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._looks_like_false_table = looks_like_false_table
        self._build_header_meta = build_header_meta
        self._to_float_or_none = to_float_or_none

    def build_tables_from_vision_payload(
        self,
        payload: Dict[str, Any],
        page_no: int,
        table_idx: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> Tuple[TableBlocks, int]:
        tables_raw = payload.get("tables", [])
        if not isinstance(tables_raw, list):
            return [], table_idx

        built: TableBlocks = []
        for table_raw in tables_raw[: self.vision_max_tables_per_page]:
            matrix = self._vision_table_to_matrix(table_raw)
            if len(matrix) < 2:
                continue

            table_id = f"{source_prefix}_t{table_idx}"
            table_idx += 1
            raw_rows_payload: List[Dict[str, Any]] = []
            for row_idx, row_values in enumerate(matrix[: self.table_max_rows + 1], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell in enumerate(row_values[: self.table_max_cols], start=1):
                    text = self._normalize_text(str(cell or ""))
                    if not text:
                        continue
                    ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                    if ref_id in bbox_map:
                        continue
                    bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    self._append_ref(parts, bbox_map, ref_id, text, bbox)
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": text,
                            "ref_id": ref_id,
                            "bbox": bbox,
                        }
                    )
                if cells_payload:
                    raw_rows_payload.append({"row_index": row_idx, "cells": cells_payload})
            if len(raw_rows_payload) < 2:
                continue

            caption = ""
            notes: List[str] = []
            if isinstance(table_raw, dict):
                caption = self._normalize_text(str(table_raw.get("caption") or table_raw.get("title") or ""))
                notes = self._safe_text_list(table_raw.get("notes"), max_items=4, max_len=120)

            headers, data_rows = self._infer_headers_and_data_rows(raw_rows_payload)
            headers, data_rows = self._recover_low_signal_headers(
                headers,
                data_rows,
                caption=caption,
                notes=notes,
            )
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if len(data_rows) < self.ocr_table_min_rows:
                continue
            if self._looks_like_false_table(headers, data_rows):
                continue

            confidence = self._to_float_or_none(table_raw.get("confidence")) if isinstance(table_raw, dict) else None
            if confidence is None:
                confidence = 0.74
            confidence = max(0.1, min(1.0, float(confidence)))

            built.append(
                {
                    "table_id": table_id,
                    "source": source_prefix,
                    "page": page_no,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(row.get("cells", [])) for row in data_rows), default=0),
                    "quality": round(confidence, 4),
                }
            )

        return built, table_idx

    @staticmethod
    def _append_ref(
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        ref_id: str,
        text: str,
        bbox: List[float],
    ) -> None:
        if ref_id not in bbox_map:
            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
            bbox_map[ref_id] = bbox
