from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

try:
    from app.core.table.table_header_runtime import TableHeaderRuntime
except ModuleNotFoundError:
    _table_header_runtime_path = Path(__file__).resolve().with_name("table_header_runtime.py")
    _table_header_runtime_spec = importlib.util.spec_from_file_location(
        "_smart_doc_flow_module2_table_header_runtime",
        _table_header_runtime_path,
    )
    if not _table_header_runtime_spec or not _table_header_runtime_spec.loader:
        raise
    _table_header_runtime_module = importlib.util.module_from_spec(_table_header_runtime_spec)
    sys.modules["_smart_doc_flow_module2_table_header_runtime"] = _table_header_runtime_module
    _table_header_runtime_spec.loader.exec_module(_table_header_runtime_module)
    TableHeaderRuntime = _table_header_runtime_module.TableHeaderRuntime

try:
    from app.core.table.table_metadata import extract_number_meta
except ModuleNotFoundError:
    _table_metadata_path = Path(__file__).resolve().with_name("table_metadata.py")
    _table_metadata_spec = importlib.util.spec_from_file_location(
        "_smart_doc_flow_module2_table_metadata",
        _table_metadata_path,
    )
    if not _table_metadata_spec or not _table_metadata_spec.loader:
        raise
    _table_metadata_module = importlib.util.module_from_spec(_table_metadata_spec)
    sys.modules["_smart_doc_flow_module2_table_metadata"] = _table_metadata_module
    _table_metadata_spec.loader.exec_module(_table_metadata_module)
    extract_number_meta = _table_metadata_module.extract_number_meta


TableBlocks = List[Dict[str, Any]]
RowsPayload = List[Dict[str, Any]]
NormalizeText = Callable[[str], str]
NormalizeTokenForCompare = Callable[[str], str]
TextPredicate = Callable[[str], bool]
DropRedundantHeaderRows = Callable[[RowsPayload, List[str]], RowsPayload]


class TableMergeRuntime:
    """Merge table fragments across same-page and cross-page boundaries."""

    def __init__(
        self,
        *,
        table_merge_max_page_gap: int,
        table_merge_header_sim: float,
        table_merge_col_overlap: float,
        normalize_text: NormalizeText,
        normalize_token_for_compare: NormalizeTokenForCompare,
        is_page_number_token: TextPredicate,
        drop_redundant_header_like_rows: DropRedundantHeaderRows,
    ) -> None:
        self.table_merge_max_page_gap = int(table_merge_max_page_gap or 0)
        self.table_merge_header_sim = float(table_merge_header_sim or 0.0)
        self.table_merge_col_overlap = float(table_merge_col_overlap or 0.0)
        self._normalize_text = normalize_text
        self._normalize_token_for_compare = normalize_token_for_compare
        self._is_page_number_token = is_page_number_token
        self._drop_redundant_header_like_rows = drop_redundant_header_like_rows

    def merge_same_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda table: (
                int(table.get("page", 0) or 0),
                self.table_vertical_span(table)[0],
                str(table.get("table_id", "")),
            ),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self.should_merge_same_page_tables(prev, table):
                merged[-1] = self.merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def merge_cross_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda table: (int(table.get("page", 0) or 0), str(table.get("table_id", ""))),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self.should_repair_cross_page_continuation(prev, table):
                merged.append(self.repair_cross_page_continuation(prev, table))
                continue
            if self.should_merge_tables(prev, table):
                merged[-1] = self.merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def table_headers_need_recovery(self, table: Dict[str, Any]) -> bool:
        headers = [self._normalize_text(str(item or "")) for item in table.get("headers", [])]
        normalized = [item for item in headers if item]
        if not normalized:
            return True

        generic_count = sum(1 for item in normalized if TableHeaderRuntime.header_token_is_generic(item))
        numeric_like_count = sum(1 for item in normalized if TableHeaderRuntime.cell_text_numeric_like(item))
        temporal_like_count = sum(
            1
            for item in normalized
            if re.fullmatch(r"(?:19|20)\d{2}年?", item)
            or re.fullmatch(r"(?:19|20)\d{2}[-/.年]?\d{1,2}(?:[-/.月]?\d{1,2}日?)?", item)
        )
        if generic_count <= 0:
            if numeric_like_count > 0 and temporal_like_count < numeric_like_count:
                return (numeric_like_count / float(max(len(normalized), 1))) >= 0.4
            return False
        meaningful_count = len(normalized) - generic_count
        if meaningful_count <= 0:
            return True
        return (generic_count / float(max(len(normalized), 1))) >= 0.5

    def _table_caption_text(self, table: Dict[str, Any]) -> str:
        return self._normalize_text(str(table.get("caption", "") or ""))

    def _table_header_values(self, table: Dict[str, Any]) -> List[str]:
        return [self._normalize_text(str(item or "")) for item in table.get("headers", [])]

    def _header_meta_for_headers(self, table: Dict[str, Any], headers: List[str]) -> List[Dict[str, Any]]:
        raw_meta = table.get("header_meta", [])
        if isinstance(raw_meta, list) and raw_meta:
            meta: List[Dict[str, Any]] = []
            for item in raw_meta:
                if not isinstance(item, dict):
                    continue
                col_index = int(item.get("col_index", 0) or 0)
                if col_index <= 0:
                    continue
                meta.append(
                    {
                        "col_index": col_index,
                        "name": self._normalize_text(str(item.get("name", "") or "")),
                        "name_norm": self._normalize_token_for_compare(str(item.get("name", "") or "")),
                        "unit": self._normalize_text(str(item.get("unit", "") or "")) or None,
                    }
                )
            if meta:
                return meta
        return [
            {
                "col_index": idx,
                "name": self._normalize_text(header),
                "name_norm": self._normalize_token_for_compare(header),
                "unit": None,
            }
            for idx, header in enumerate(headers, start=1)
        ]

    def _header_values_look_like_data_row(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        values = [value for value in self._table_header_values(curr) if value]
        if not values:
            return False

        numeric_count = sum(1 for value in values if TableHeaderRuntime.cell_text_numeric_like(value))
        temporal_count = sum(1 for value in values if re.fullmatch(r"(?:19|20)\d{2}年?", value))
        if numeric_count <= 0:
            return False

        prev_headers = [value for value in self._table_header_values(prev) if value]
        prev_first = prev_headers[0] if prev_headers else ""
        curr_first = values[0]
        if prev_first and not TableHeaderRuntime.cell_text_numeric_like(prev_first):
            if TableHeaderRuntime.header_token_is_generic(curr_first):
                return False
            if TableHeaderRuntime.cell_text_numeric_like(curr_first):
                return False
            trailing_numeric = sum(
                1 for value in values[1:] if TableHeaderRuntime.cell_text_numeric_like(value)
            )
            return trailing_numeric >= 1

        return numeric_count >= max(1, len(values) - 1) and temporal_count < numeric_count

    def _row_values(self, row: Dict[str, Any]) -> List[str]:
        if not isinstance(row, dict):
            return []
        cells = row.get("cells", [])
        if not isinstance(cells, list):
            return []
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

    def _first_row_looks_like_cross_page_continuation(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        rows = curr.get("rows", [])
        if not isinstance(rows, list) or not rows:
            return False
        first_row_values = self._row_values(rows[0])
        if not first_row_values:
            return False
        return self._header_values_look_like_data_row(prev, {"headers": first_row_values})

    def should_repair_cross_page_continuation(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        prev_page = int(prev.get("page", 0) or 0)
        curr_page = int(curr.get("page", 0) or 0)
        if prev_page <= 0 or curr_page <= prev_page:
            return False

        page_gap = curr_page - prev_page
        if page_gap > max(1, self.table_merge_max_page_gap):
            return False

        if self.table_headers_need_recovery(prev):
            return False
        if not self.table_headers_need_recovery(curr):
            return False
        prev_caption = self._table_caption_text(prev)
        curr_caption = self._table_caption_text(curr)
        if curr_caption and prev_caption and curr_caption != prev_caption:
            return False
        header_values_look_like_data = self._header_values_look_like_data_row(prev, curr)
        first_row_looks_like_continuation = False
        if not header_values_look_like_data and not curr_caption:
            first_row_looks_like_continuation = self._first_row_looks_like_cross_page_continuation(prev, curr)
        if not header_values_look_like_data and not first_row_looks_like_continuation:
            return False

        col_overlap = self.table_col_overlap(prev, curr)
        if col_overlap < max(0.72, self.table_merge_col_overlap * 0.9):
            return False

        _, prev_bottom = self.table_vertical_span(prev)
        curr_top, _ = self.table_vertical_span(curr)
        if prev_bottom < 0.72 or curr_top > 0.30:
            return False

        if self.table_row_count(prev) < 2:
            return False
        return True

    def _row_bbox_hint(self, table: Dict[str, Any]) -> List[float]:
        page = int(table.get("page", 0) or 0)
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                bbox = cell.get("bbox")
                if isinstance(bbox, list) and len(bbox) >= 5:
                    return [float(value) for value in bbox[:5]]
        bbox_norm = table.get("bbox_norm")
        if isinstance(bbox_norm, list) and len(bbox_norm) >= 4 and page > 0:
            return [float(page)] + [float(value) for value in bbox_norm[:4]]
        return [float(page if page > 0 else 1), 0.0, 0.0, 1.0, 1.0]

    def _redecorate_rows(
        self,
        rows_payload: RowsPayload,
        *,
        header_meta: List[Dict[str, Any]],
        row_index_start: int = 1,
    ) -> RowsPayload:
        header_map = {
            int(item.get("col_index", 0) or 0): item
            for item in header_meta
            if isinstance(item, dict) and int(item.get("col_index", 0) or 0) > 0
        }
        decorated: RowsPayload = []
        next_row_index = max(1, int(row_index_start or 1))
        for row in rows_payload:
            if not isinstance(row, dict):
                continue
            source_row_index = int(row.get("source_row_index", row.get("row_index", next_row_index)) or next_row_index)
            cells_out: List[Dict[str, Any]] = []
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                col_index = int(cell.get("col_index", 0) or 0)
                if col_index <= 0:
                    continue
                text = self._normalize_text(str(cell.get("text", "") or ""))
                if not text:
                    continue
                header = header_map.get(
                    col_index,
                    {
                        "name": f"col_{col_index}",
                        "name_norm": "",
                        "unit": None,
                    },
                )
                number_meta = extract_number_meta(text, header.get("unit"))
                copied = dict(cell)
                copied.update(
                    {
                        "col_index": col_index,
                        "text": text,
                        "header": header.get("name"),
                        "header_norm": header.get("name_norm"),
                        "header_unit": header.get("unit"),
                        "value_type": number_meta.get("value_type"),
                        "numeric_value": number_meta.get("numeric_value"),
                        "ratio_value": number_meta.get("ratio_value"),
                        "detected_unit": number_meta.get("detected_unit"),
                        "normalized_text": number_meta.get("normalized_text"),
                    }
                )
                cells_out.append(copied)
            if not cells_out:
                continue
            decorated.append(
                {
                    "row_index": next_row_index,
                    "source_row_index": source_row_index,
                    "cells": cells_out,
                }
            )
            next_row_index += 1
        return decorated

    def _header_row_as_data_payload(
        self,
        header_values: List[str],
        *,
        header_meta: List[Dict[str, Any]],
        bbox: List[float],
    ) -> Optional[Dict[str, Any]]:
        cells: List[Dict[str, Any]] = []
        for col_index, text in enumerate(header_values, start=1):
            text = self._normalize_text(text)
            if not text:
                continue
            header = next(
                (
                    item
                    for item in header_meta
                    if isinstance(item, dict) and int(item.get("col_index", 0) or 0) == col_index
                ),
                {
                    "name": f"col_{col_index}",
                    "name_norm": "",
                    "unit": None,
                },
            )
            number_meta = extract_number_meta(text, header.get("unit"))
            cells.append(
                {
                    "col_index": col_index,
                    "text": text,
                    "bbox": list(bbox),
                    "header": header.get("name"),
                    "header_norm": header.get("name_norm"),
                    "header_unit": header.get("unit"),
                    "value_type": number_meta.get("value_type"),
                    "numeric_value": number_meta.get("numeric_value"),
                    "ratio_value": number_meta.get("ratio_value"),
                    "detected_unit": number_meta.get("detected_unit"),
                    "normalized_text": number_meta.get("normalized_text"),
                }
            )
        if not cells:
            return None
        return {
            "row_index": 1,
            "source_row_index": 0,
            "cells": cells,
        }

    def repair_cross_page_continuation(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        repaired = dict(curr)
        prev_headers = [self._normalize_text(str(item or "")) for item in prev.get("headers", [])]
        prev_headers = [item for item in prev_headers if item]
        if not prev_headers:
            return repaired

        prev_header_meta = self._header_meta_for_headers(prev, prev_headers)
        curr_header_values = self._table_header_values(curr)
        curr_rows = curr.get("rows", []) if isinstance(curr.get("rows"), list) else []
        repaired_rows = self._redecorate_rows(curr_rows, header_meta=prev_header_meta, row_index_start=1)

        if self._header_values_look_like_data_row(prev, curr):
            synthetic_row = self._header_row_as_data_payload(
                curr_header_values[: len(prev_headers)],
                header_meta=prev_header_meta,
                bbox=self._row_bbox_hint(curr),
            )
            if synthetic_row:
                repaired_rows = [synthetic_row] + self._redecorate_rows(
                    curr_rows,
                    header_meta=prev_header_meta,
                    row_index_start=2,
                )

        repaired["headers"] = list(prev_headers)
        repaired["header_meta"] = prev_header_meta
        repaired["rows"] = repaired_rows
        repaired["row_count"] = len(repaired_rows)
        repaired["col_count"] = max(
            len(prev_headers),
            int(curr.get("col_count", 0) or 0),
            max((len(row.get("cells", [])) for row in repaired_rows), default=0),
        )

        prev_caption = self._table_caption_text(prev)
        curr_caption = self._table_caption_text(curr)
        if prev_caption and not curr_caption:
            repaired["caption"] = prev_caption

        repaired["continuation_of"] = str(prev.get("table_id", "") or "")
        repaired["continuation_page_gap"] = int(curr.get("page", 0) or 0) - int(prev.get("page", 0) or 0)
        inherited_notes: List[str] = []
        for item in prev.get("notes", []):
            text = self._normalize_text(str(item or ""))
            if text:
                inherited_notes.append(text)
        if inherited_notes and not repaired.get("notes"):
            repaired["notes"] = inherited_notes[:4]
        return repaired

    def effective_header_tokens(self, table: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        header_meta = table.get("header_meta", [])
        if isinstance(header_meta, list) and header_meta:
            for item in header_meta:
                name = self._normalize_text(str(item.get("name", "")))
                if not name:
                    continue
                if TableHeaderRuntime.header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        if not tokens:
            for raw in table.get("headers", []):
                name = self._normalize_text(str(raw or ""))
                if not name:
                    continue
                if TableHeaderRuntime.header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        return tokens

    def header_similarity(self, left: List[str], right: List[str]) -> float:
        if not left or not right:
            return 0.0

        left_tokens = [self._normalize_token_for_compare(item) for item in left]
        right_tokens = [self._normalize_token_for_compare(item) for item in right]
        left_tokens = [item for item in left_tokens if item]
        right_tokens = [item for item in right_tokens if item]
        if not left_tokens or not right_tokens:
            return 0.0

        left_set = set(left_tokens)
        right_set = set(right_tokens)
        inter = len(left_set & right_set)
        union = len(left_set | right_set)
        jaccard = (inter / float(union)) if union else 0.0

        short, long = (left_tokens, right_tokens) if len(left_tokens) <= len(right_tokens) else (right_tokens, left_tokens)
        order_hit = 0
        for idx, token in enumerate(short):
            if idx < len(long) and token == long[idx]:
                order_hit += 1
        order_score = order_hit / float(max(len(short), 1))
        return (0.65 * jaccard) + (0.35 * order_score)

    @staticmethod
    def table_col_overlap(left: Dict[str, Any], right: Dict[str, Any]) -> float:
        left_cols = int(left.get("col_count", 0) or 0)
        right_cols = int(right.get("col_count", 0) or 0)
        if left_cols <= 0:
            left_cols = max((len(row.get("cells", [])) for row in left.get("rows", [])), default=0)
        if right_cols <= 0:
            right_cols = max((len(row.get("cells", [])) for row in right.get("rows", [])), default=0)
        if left_cols <= 0 or right_cols <= 0:
            return 0.0
        return min(left_cols, right_cols) / float(max(left_cols, right_cols))

    @staticmethod
    def table_vertical_span(table: Dict[str, Any]) -> Tuple[float, float]:
        y0 = 1.0
        y1 = 0.0
        hit = False
        for row in table.get("rows", []):
            for cell in row.get("cells", []):
                bbox = cell.get("bbox", [])
                if not isinstance(bbox, list) or len(bbox) < 5:
                    continue
                try:
                    y = float(bbox[2])
                    height = float(bbox[4])
                except (TypeError, ValueError):
                    continue
                if height < 0:
                    continue
                y0 = min(y0, y)
                y1 = max(y1, y + height)
                hit = True
        if not hit:
            return 0.0, 1.0
        return max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))

    @staticmethod
    def table_row_count(table: Dict[str, Any]) -> int:
        try:
            row_count = int(table.get("row_count", 0) or 0)
        except (TypeError, ValueError):
            row_count = 0
        if row_count > 0:
            return row_count
        return len(table.get("rows", []))

    @staticmethod
    def table_has_continuation_marker(table: Dict[str, Any]) -> bool:
        headers = [str(item or "").strip().lower() for item in table.get("headers", []) if str(item or "").strip()]
        if not headers:
            return False
        text = " ".join(headers)
        return ("continued" in text) or ("cont." in text) or ("\u7eed\u8868" in text)

    @staticmethod
    def extract_table_label(table: Dict[str, Any]) -> str:
        headers = [str(item or "").strip() for item in table.get("headers", []) if str(item or "").strip()]
        if not headers:
            return ""
        text = " ".join(headers)
        match = re.search(r"\btable\s+([A-Za-z]?[0-9]+(?:[-.][A-Za-z0-9]+)?)\b", text, re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).lower()

    def should_merge_same_page_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        prev_page = int(prev.get("page", 0) or 0)
        curr_page = int(curr.get("page", 0) or 0)
        if prev_page <= 0 or curr_page <= 0 or prev_page != curr_page:
            return False

        header_sim = self.header_similarity(self.effective_header_tokens(prev), self.effective_header_tokens(curr))
        col_overlap = self.table_col_overlap(prev, curr)
        if col_overlap < 0.5:
            return False

        prev_top, prev_bottom = self.table_vertical_span(prev)
        curr_top, curr_bottom = self.table_vertical_span(curr)
        if curr_bottom <= prev_top:
            gap = prev_top - curr_bottom
        elif curr_top >= prev_bottom:
            gap = curr_top - prev_bottom
        else:
            gap = 0.0
        if gap > 0.09:
            return False

        continuation = self.table_has_continuation_marker(prev) or self.table_has_continuation_marker(curr)
        tiny_fragment = self.table_row_count(prev) <= 2 or self.table_row_count(curr) <= 2

        if col_overlap >= 0.86 and gap <= 0.035 and (header_sim >= 0.16 or continuation or tiny_fragment):
            return True
        if col_overlap >= 0.74 and gap <= 0.06 and (header_sim >= 0.32 or continuation or tiny_fragment):
            return True
        return False

    def should_merge_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        prev_page = int(prev.get("page", 0) or 0)
        curr_page = int(curr.get("page", 0) or 0)
        if prev_page <= 0 or curr_page <= 0 or curr_page < prev_page:
            return False

        left_headers = self.effective_header_tokens(prev)
        right_headers = self.effective_header_tokens(curr)
        header_sim = self.header_similarity(left_headers, right_headers)
        col_overlap = self.table_col_overlap(prev, curr)
        page_gap = curr_page - prev_page
        _, prev_bottom = self.table_vertical_span(prev)
        curr_top, _ = self.table_vertical_span(curr)

        if page_gap <= self.table_merge_max_page_gap:
            if header_sim >= self.table_merge_header_sim and col_overlap >= self.table_merge_col_overlap:
                return True

            continuation = self.table_has_continuation_marker(prev) or self.table_has_continuation_marker(curr)
            if continuation and header_sim >= (self.table_merge_header_sim * 0.75) and col_overlap >= 0.5:
                return True
            if prev_bottom >= 0.78 and curr_top <= 0.26 and col_overlap >= 0.72:
                prev_label = self.extract_table_label(prev)
                curr_label = self.extract_table_label(curr)
                same_label = bool(prev_label and curr_label and prev_label == curr_label)
                if continuation or same_label:
                    return True
                if header_sim >= max(0.58, self.table_merge_header_sim + 0.08):
                    return True
                if self.table_row_count(curr) <= 3 and header_sim >= 0.68:
                    return True

        relaxed_gap = max(self.table_merge_max_page_gap, self.table_merge_max_page_gap * 4)
        if page_gap <= relaxed_gap and header_sim >= 0.9 and col_overlap >= 0.8:
            return True

        if page_gap <= max(10, relaxed_gap):
            prev_label = self.extract_table_label(prev)
            curr_label = self.extract_table_label(curr)
            if prev_label and curr_label and prev_label == curr_label and col_overlap >= 0.5:
                return True

        return False

    def merge_table_pair(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(prev)
        prev_rows = prev.get("rows", []) if isinstance(prev.get("rows", []), list) else []
        curr_rows = curr.get("rows", []) if isinstance(curr.get("rows", []), list) else []
        prev_page = int(prev.get("page", 0) or 0)
        curr_page = int(curr.get("page", 0) or 0)

        if prev_page > 0 and curr_page > 0 and prev_page != curr_page:
            prev_headers = [str(item) for item in prev.get("headers", [])]
            if prev_headers:
                curr_rows = self._drop_redundant_header_like_rows(curr_rows, prev_headers)

        out_rows: RowsPayload = []
        row_idx = 1
        for row in prev_rows + curr_rows:
            cells = row.get("cells", []) if isinstance(row.get("cells", []), list) else []
            cells_out = [dict(cell) for cell in cells if isinstance(cell, dict)]
            if not cells_out:
                continue
            out_rows.append({"row_index": row_idx, "cells": cells_out})
            row_idx += 1

        merged["rows"] = out_rows
        merged["row_count"] = len(out_rows)
        merged["col_count"] = max(
            int(prev.get("col_count", 0) or 0),
            int(curr.get("col_count", 0) or 0),
            max((len(row.get("cells", [])) for row in out_rows), default=0),
        )

        left_headers = self.effective_header_tokens(prev)
        right_headers = self.effective_header_tokens(curr)
        if len(right_headers) > len(left_headers):
            merged["headers"] = curr.get("headers", merged.get("headers", []))
            merged["header_meta"] = curr.get("header_meta", merged.get("header_meta", []))

        try:
            prev_quality = float(prev.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            prev_quality = 0.0
        try:
            curr_quality = float(curr.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            curr_quality = 0.0
        if (prev_quality > 0.0) or (curr_quality > 0.0):
            merged["quality"] = round((prev_quality + curr_quality) / 2.0, 4)

        start = min(value for value in [prev_page, curr_page] if value > 0) if (prev_page > 0 or curr_page > 0) else 0
        end = max(prev_page, curr_page)
        if start > 0 and end >= start:
            merged["page"] = start
            merged["page_span"] = [start, end]

        merged_from: List[str] = []
        for item in prev.get("merged_from", []):
            if item:
                merged_from.append(str(item))
        prev_id = str(prev.get("table_id", ""))
        curr_id = str(curr.get("table_id", ""))
        if prev_id and prev_id not in merged_from:
            merged_from.append(prev_id)
        if curr_id and curr_id not in merged_from:
            merged_from.append(curr_id)
        if merged_from:
            merged["merged_from"] = merged_from

        return merged
