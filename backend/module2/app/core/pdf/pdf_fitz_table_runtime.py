from __future__ import annotations

from html import escape
import re
from typing import Any, Callable, Dict, List, Tuple


TableBlocks = List[Dict[str, Any]]
PartsPayload = List[str]
BboxMap = Dict[str, List[float]]
NormalizeText = Callable[[str], str]
InferHeadersAndDataRows = Callable[[List[Dict[str, Any]]], Tuple[List[str], List[Dict[str, Any]]]]
DropRedundantHeaderRows = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
DecorateRowsWithMeta = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
MergeTables = Callable[[TableBlocks], TableBlocks]


class PdfFitzTableRuntime:
    """Extract native PDF tables via PyMuPDF table finder without parser-specific state."""

    _CAPTION_LINE_RE = re.compile(r"^(?:表|table)\s*[A-Za-z0-9一二三四五六七八九十]+", re.IGNORECASE)

    @staticmethod
    def _default_infer_headers_and_data_rows(
        rows_payload: List[Dict[str, Any]],
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        rows = rows_payload if isinstance(rows_payload, list) else []
        if not rows:
            return [], []
        first_row = rows[0] if isinstance(rows[0], dict) else {}
        cells = first_row.get("cells", []) if isinstance(first_row, dict) else []
        if not isinstance(cells, list):
            return [], rows[1:]
        header_by_index: Dict[int, str] = {}
        max_col = 0
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            try:
                col_index = int(cell.get("col_index", 0) or 0)
            except (TypeError, ValueError):
                col_index = 0
            if col_index <= 0:
                continue
            max_col = max(max_col, col_index)
            header_text = str(cell.get("text", "") or "").strip()
            header_by_index[col_index] = header_text or f"col_{col_index}"
        headers = [header_by_index.get(index, f"col_{index}") for index in range(1, max_col + 1)]
        data_rows: List[Dict[str, Any]] = []
        for row_index, raw_row in enumerate(rows[1:], start=1):
            if not isinstance(raw_row, dict):
                continue
            cells_payload = raw_row.get("cells", [])
            if not isinstance(cells_payload, list):
                continue
            data_rows.append(
                {
                    "row_index": row_index,
                    "cells": [dict(cell) for cell in cells_payload if isinstance(cell, dict)],
                }
            )
        return headers, data_rows

    @staticmethod
    def _default_drop_redundant_header_like_rows(
        rows_payload: List[Dict[str, Any]],
        _headers: List[str],
    ) -> List[Dict[str, Any]]:
        return rows_payload if isinstance(rows_payload, list) else []

    def __init__(
        self,
        *,
        table_max_rows: int,
        table_max_cols: int,
        table_cell_cap: int,
        table_merge_enable: bool,
        normalize_text: NormalizeText,
        infer_headers_and_data_rows: InferHeadersAndDataRows | None = None,
        drop_redundant_header_like_rows: DropRedundantHeaderRows | None = None,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        build_header_meta: BuildHeaderMeta,
        merge_same_page_tables: MergeTables,
        merge_cross_page_tables: MergeTables,
    ) -> None:
        self.table_max_rows = max(1, int(table_max_rows or 1))
        self.table_max_cols = max(1, int(table_max_cols or 1))
        self.table_cell_cap = max(1, int(table_cell_cap or 1))
        self.table_merge_enable = bool(table_merge_enable)
        self._normalize_text = normalize_text
        self._infer_headers_and_data_rows = (
            infer_headers_and_data_rows
            if callable(infer_headers_and_data_rows)
            else self._default_infer_headers_and_data_rows
        )
        self._drop_redundant_header_like_rows = (
            drop_redundant_header_like_rows
            if callable(drop_redundant_header_like_rows)
            else self._default_drop_redundant_header_like_rows
        )
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._build_header_meta = build_header_meta
        self._merge_same_page_tables = merge_same_page_tables
        self._merge_cross_page_tables = merge_cross_page_tables

    def extract_pdf_tables_with_fitz(
        self,
        file_bytes: bytes,
        page_count: int,
        parts: PartsPayload,
        bbox_map: BboxMap,
        merge_tables: bool = True,
    ) -> TableBlocks:
        try:
            import fitz  # pymupdf
        except Exception:
            return []

        table_blocks: TableBlocks = []
        emitted_cells = 0
        table_idx = 1

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            return []

        try:
            for page_idx in range(min(max(page_count, 0), len(doc))):
                page = doc.load_page(page_idx)
                page_no = page_idx + 1
                if not hasattr(page, "find_tables"):
                    continue

                try:
                    finder = page.find_tables()
                except Exception:
                    continue

                tables = getattr(finder, "tables", None) or []
                for table in tables:
                    if emitted_cells >= self.table_cell_cap:
                        break

                    try:
                        matrix = table.extract()
                    except Exception:
                        continue
                    if not matrix or len(matrix) < 2:
                        continue

                    rows_cleaned: List[List[str]] = []
                    for row in matrix[: self.table_max_rows + 1]:
                        values: List[str] = []
                        for cell in list(row)[: self.table_max_cols]:
                            text = self._normalize_text("" if cell is None else str(cell))
                            values.append(text)
                        if any(values):
                            rows_cleaned.append(values)
                    if len(rows_cleaned) < 2:
                        continue

                    table_id = f"pdf_fitz_t{table_idx}"
                    page_rect = getattr(page, "rect", None)
                    table_bbox = self.normalize_table_bbox(
                        getattr(table, "bbox", None),
                        getattr(page_rect, "width", 0.0),
                        getattr(page_rect, "height", 0.0),
                    )

                    raw_rows_payload = self._build_rows_payload(rows_cleaned)
                    headers, data_rows = self._infer_headers_and_data_rows(raw_rows_payload)
                    headers, caption_hint = self._recover_headers_from_previous_page_text(
                        doc=doc,
                        page_idx=page_idx,
                        table_bbox=table_bbox,
                        headers=headers,
                        rows_payload=data_rows or raw_rows_payload,
                    )
                    if not headers:
                        header_width = min(
                            self.table_max_cols,
                            max(len(rows_cleaned[0]), max((len(row) for row in rows_cleaned[1:]), default=0)),
                        )
                        header_seed = rows_cleaned[0] + ([""] * max(0, header_width - len(rows_cleaned[0])))
                        headers = [
                            (self._normalize_text(raw_header) or f"col_{idx}")
                            for idx, raw_header in enumerate(header_seed[:header_width], start=1)
                        ]
                        data_rows = raw_rows_payload[1:]
                    data_rows = self._drop_redundant_header_like_rows(data_rows, headers)

                    rows_payload: List[Dict[str, Any]] = []
                    for row_idx, row in enumerate(data_rows, start=1):
                        source_row_index = int(row.get("row_index", row_idx) or row_idx)
                        cells_payload: List[Dict[str, Any]] = []
                        cells = sorted(
                            row.get("cells", []),
                            key=lambda cell: int(cell.get("col_index", 0) or 0),
                        )
                        for cell in cells[: self.table_max_cols]:
                            col_idx = int(cell.get("col_index", 0) or 0)
                            text = self._normalize_text(str(cell.get("text", "") or ""))
                            if col_idx <= 0:
                                continue
                            if not text:
                                continue
                            ref_id = f"{table_id}_r{source_row_index}_c{col_idx}"
                            if ref_id in bbox_map:
                                continue
                            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
                            bbox = [float(page_no), table_bbox[0], table_bbox[1], table_bbox[2], table_bbox[3]]
                            bbox_map[ref_id] = bbox
                            cells_payload.append(
                                {
                                    "col_index": col_idx,
                                    "text": text,
                                    "ref_id": ref_id,
                                    "bbox": bbox,
                                }
                            )
                            emitted_cells += 1
                            if emitted_cells >= self.table_cell_cap:
                                break
                        if cells_payload:
                            rows_payload.append({"row_index": source_row_index, "cells": cells_payload})
                        if emitted_cells >= self.table_cell_cap:
                            break

                    if rows_payload:
                        rows_payload = self._decorate_rows_with_meta(rows_payload, headers)
                        table_blocks.append(
                            {
                                "table_id": table_id,
                                "source": "pdf_fitz",
                                "page": page_no,
                                "bbox_norm": [table_bbox[0], table_bbox[1], table_bbox[2], table_bbox[3]],
                                "headers": headers,
                                "header_meta": self._build_header_meta(headers),
                                "rows": rows_payload,
                                "row_count": len(rows_payload),
                                "col_count": max((len(row.get("cells", [])) for row in rows_payload), default=0),
                                "caption": caption_hint or None,
                            }
                        )
                        table_idx += 1

                if emitted_cells >= self.table_cell_cap:
                    break
        finally:
            doc.close()

        if table_blocks and self.table_merge_enable and merge_tables:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    def _build_rows_payload(self, matrix: List[List[str]]) -> List[Dict[str, Any]]:
        rows_payload: List[Dict[str, Any]] = []
        for row_idx, values in enumerate(matrix, start=1):
            cells_payload: List[Dict[str, Any]] = []
            for col_idx, text in enumerate(values[: self.table_max_cols], start=1):
                normalized = self._normalize_text(text)
                if not normalized:
                    continue
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": normalized,
                    }
                )
            if cells_payload:
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})
        return rows_payload

    def _recover_headers_from_previous_page_text(
        self,
        *,
        doc: Any,
        page_idx: int,
        table_bbox: Tuple[float, float, float, float],
        headers: List[str],
        rows_payload: List[Dict[str, Any]],
    ) -> Tuple[List[str], str]:
        if page_idx <= 0:
            return headers, ""
        if not self._headers_look_generic(headers):
            return headers, ""
        if not rows_payload:
            return headers, ""
        if float(table_bbox[1]) > 0.18:
            return headers, ""

        try:
            prev_page = doc.load_page(page_idx - 1)
        except Exception:
            return headers, ""
        if not hasattr(prev_page, "get_text"):
            return headers, ""

        try:
            prev_text = prev_page.get_text("text") or ""
        except Exception:
            return headers, ""

        lines = [self._normalize_text(line) for line in str(prev_text).splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return headers, ""

        col_count = max(len(headers), len(self._row_values(rows_payload[0])))
        if col_count <= 1:
            return headers, ""

        tail = lines[-min(len(lines), 64) :]
        current_first_row = self._row_values(rows_payload[0])
        if not self._looks_like_data_row(current_first_row):
            return headers, ""

        for index in range(len(tail) - 1, -1, -1):
            caption = tail[index]
            if not self._CAPTION_LINE_RE.search(caption):
                continue
            remaining = tail[index + 1 :]
            if len(remaining) < (col_count * 2):
                continue
            candidate_headers = remaining[:col_count]
            candidate_first_row = remaining[col_count : (col_count * 2)]
            if not self._looks_like_header_row(candidate_headers):
                continue
            if not self._looks_like_data_row(candidate_first_row):
                continue
            if not self._row_shapes_are_compatible(candidate_first_row, current_first_row):
                continue
            return candidate_headers, caption

        return headers, ""

    def _headers_look_generic(self, headers: List[str]) -> bool:
        normalized = [self._normalize_text(value) for value in headers if self._normalize_text(value)]
        if not normalized:
            return True
        generic_count = 0
        for value in normalized:
            compact = re.sub(r"[\s_\-]+", "", value.lower())
            if compact.startswith("col") and compact[3:].isdigit():
                generic_count += 1
                continue
            if value.startswith("数值_") or value.startswith("类别_"):
                generic_count += 1
        return generic_count >= max(1, len(normalized) - 1)

    def _row_values(self, row: Dict[str, Any]) -> List[str]:
        cells = row.get("cells", []) if isinstance(row, dict) else []
        ordered = sorted(
            (cell for cell in cells if isinstance(cell, dict)),
            key=lambda cell: int(cell.get("col_index", 0) or 0),
        )
        values: List[str] = []
        for cell in ordered:
            text = self._normalize_text(str(cell.get("text", "") or ""))
            if text:
                values.append(text)
        return values

    @staticmethod
    def _numeric_like(value: str) -> bool:
        probe = str(value or "").strip()
        if not probe:
            return False
        compact = re.sub(r"[\s,，]", "", probe)
        return bool(re.fullmatch(r"[-+]?\d*\.?\d+(?:[%％])?", compact))

    def _looks_like_header_row(self, values: List[str]) -> bool:
        cleaned = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not cleaned:
            return False
        if self._numeric_like(cleaned[0]):
            return False
        numeric_count = sum(1 for value in cleaned if self._numeric_like(value))
        return numeric_count < max(1, len(cleaned) - 1)

    def _looks_like_data_row(self, values: List[str]) -> bool:
        cleaned = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if len(cleaned) < 2:
            return False
        if self._numeric_like(cleaned[0]):
            return False
        numeric_count = sum(1 for value in cleaned[1:] if self._numeric_like(value))
        return numeric_count >= max(1, len(cleaned[1:]) - 1)

    def _row_shapes_are_compatible(self, left: List[str], right: List[str]) -> bool:
        if len(left) != len(right):
            return False
        left_flags = [self._numeric_like(value) for value in left]
        right_flags = [self._numeric_like(value) for value in right]
        return left_flags == right_flags

    @staticmethod
    def normalize_table_bbox(raw_bbox: Any, width: float, height: float) -> Tuple[float, float, float, float]:
        if not raw_bbox or not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return 0.0, 0.0, 1.0, 1.0
        try:
            x0 = max(0.0, float(raw_bbox[0])) / max(float(width), 1.0)
            y0 = max(0.0, float(raw_bbox[1])) / max(float(height), 1.0)
            x1 = max(0.0, float(raw_bbox[2])) / max(float(width), 1.0)
            y1 = max(0.0, float(raw_bbox[3])) / max(float(height), 1.0)
            return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)
        except (TypeError, ValueError):
            return 0.0, 0.0, 1.0, 1.0
