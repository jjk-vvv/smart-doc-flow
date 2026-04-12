from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


RowsPayload = List[Dict[str, Any]]
TableBlock = Dict[str, Any]
NormalizeText = Callable[[str], str]
GetCells = Callable[[Any], Sequence[Any]]
GetCellText = Callable[[Any], str]
GetRowIndex = Callable[[Any, int], int]
GetColIndex = Callable[[Any, int], int]
BuildCellBbox = Callable[[int, int, Any], List[float]]
BuildCellRef = Callable[[int, int, Any], str]
AfterCell = Callable[[int, int, Any, str], None]
InferHeadersAndDataRows = Callable[[RowsPayload], Tuple[List[str], RowsPayload]]
DropRedundantHeaderRows = Callable[[RowsPayload, List[str]], RowsPayload]
DecorateRowsWithMeta = Callable[[RowsPayload, List[str]], RowsPayload]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]


class NonPdfTextRuntime:
    """Centralize non-PDF text ref emission for DOCX/XLSX style sources."""

    _DEFAULT_BBOX = [1.0, 0.0, 0.0, 1.0, 1.0]

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
    ) -> None:
        self._normalize_text = normalize_text

    def append_text_ref(
        self,
        *,
        ref_id: str,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        bbox: Sequence[float] | None = None,
    ) -> bool:
        normalized = self._normalize_text(str(text or ""))
        if not normalized:
            return False

        bbox_values = self._coerce_bbox(bbox)
        parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
        bbox_map[ref_id] = bbox_values
        return True

    def append_numbered_text_ref(
        self,
        *,
        ref_prefix: str,
        ref_idx: int,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        bbox: Sequence[float] | None = None,
    ) -> int:
        if self.append_text_ref(
            ref_id=f"{ref_prefix}_{ref_idx}",
            text=text,
            parts=parts,
            bbox_map=bbox_map,
            bbox=bbox,
        ):
            return ref_idx + 1
        return ref_idx

    def append_xlsx_sheet_placeholders(
        self,
        *,
        sheet_names: Iterable[str],
        sheet_limit: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> int:
        emitted = 0
        for idx, sheet_name in enumerate(sheet_names, start=1):
            if idx > max(1, int(sheet_limit or 1)):
                break
            safe_name = self._normalize_text(str(sheet_name or f"Sheet{idx}"))
            desc = f"工作表：{safe_name}（未检测到可提取单元格，可能为图表或公式驱动文件）"
            if self.append_text_ref(
                ref_id=f"xlsx_sheet_{idx}",
                text=desc,
                parts=parts,
                bbox_map=bbox_map,
                bbox=[float(idx), 0.0, 0.0, 1.0, 1.0],
            ):
                emitted += 1
        return emitted

    def _coerce_bbox(self, bbox: Sequence[float] | None) -> List[float]:
        if bbox is None:
            return list(self._DEFAULT_BBOX)

        values = [float(item) for item in bbox[:5]]
        if len(values) < 5:
            values.extend(self._DEFAULT_BBOX[len(values) :])
        return values[:5]


class NonPdfTableRowsRuntime:
    """Build parser-compatible row payloads from office-style table rows."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
    ) -> None:
        self._normalize_text = normalize_text

    def build_rows_payload(
        self,
        *,
        table_id: str,
        rows: Iterable[Any],
        get_cells: GetCells,
        get_cell_text: GetCellText,
        max_rows: int,
        max_cols: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        bbox: List[float] | None = None,
    ) -> RowsPayload:
        rows_payload: RowsPayload = []
        default_bbox = [1.0, 0.0, 0.0, 1.0, 1.0] if bbox is None else [float(item) for item in bbox[:5]]
        for row_idx, row in enumerate(rows, start=1):
            if row_idx > max_rows:
                break
            cells_payload: List[Dict[str, Any]] = []
            for col_idx, cell in enumerate(get_cells(row), start=1):
                if col_idx > max_cols:
                    break
                cell_text = self._normalize_text(get_cell_text(cell))
                cell_ref = None
                cell_bbox = list(default_bbox)
                if cell_text:
                    cell_ref = f"{table_id}_r{row_idx}_c{col_idx}"
                    parts.append(f'<ref id="{cell_ref}">{escape(cell_text)}</ref>')
                    bbox_map[cell_ref] = list(cell_bbox)
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": cell_text,
                        "ref_id": cell_ref,
                        "bbox": cell_bbox,
                    }
                )
            if any(cell.get("text") for cell in cells_payload):
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})
        return rows_payload

    def build_indexed_rows_payload(
        self,
        *,
        rows: Iterable[Any],
        get_cells: GetCells,
        get_cell_text: GetCellText,
        get_row_index: GetRowIndex,
        get_col_index: GetColIndex,
        build_cell_bbox: BuildCellBbox,
        build_cell_ref: BuildCellRef,
        max_rows: int,
        max_cols: int,
        emitted_cells: int,
        max_emitted_cells: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        break_on_col_overflow: bool = False,
        after_cell: AfterCell | None = None,
    ) -> Tuple[RowsPayload, int, bool]:
        rows_payload: RowsPayload = []
        hit_cap = False
        for row_pos, row in enumerate(rows, start=1):
            row_idx = int(get_row_index(row, row_pos) or row_pos)
            if row_idx > max_rows:
                break
            cells_payload: List[Dict[str, Any]] = []
            for cell_pos, cell in enumerate(get_cells(row), start=1):
                col_idx = int(get_col_index(cell, cell_pos) or cell_pos)
                if col_idx > max_cols:
                    if break_on_col_overflow:
                        break
                    continue

                text = self._normalize_text(get_cell_text(cell))
                bbox = [float(item) for item in build_cell_bbox(row_idx, col_idx, cell)[:5]]
                cell_ref = None
                if text:
                    cell_ref = build_cell_ref(row_idx, col_idx, cell)
                    parts.append(f'<ref id="{cell_ref}">{escape(text)}</ref>')
                    bbox_map[cell_ref] = list(bbox)
                    emitted_cells += 1
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": text,
                        "ref_id": cell_ref,
                        "bbox": bbox,
                    }
                )
                if after_cell is not None:
                    after_cell(row_idx, col_idx, cell, text)
                if emitted_cells >= max_emitted_cells:
                    hit_cap = True
                    break

            if any(cell.get("text") for cell in cells_payload):
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})
            if hit_cap:
                break
        return rows_payload, emitted_cells, hit_cap


class NonPdfTableRuntime:
    """Assemble DOCX/XLSX-style table payloads into parser-compatible table blocks."""

    def __init__(
        self,
        *,
        infer_headers_and_data_rows: InferHeadersAndDataRows,
        drop_redundant_header_like_rows: DropRedundantHeaderRows,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        build_header_meta: BuildHeaderMeta,
    ) -> None:
        self._infer_headers_and_data_rows = infer_headers_and_data_rows
        self._drop_redundant_header_like_rows = drop_redundant_header_like_rows
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._build_header_meta = build_header_meta

    def build_table_block(
        self,
        *,
        table_id: str,
        source: str,
        page: int,
        rows_payload: RowsPayload,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[TableBlock]:
        if not rows_payload:
            return None

        headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
        data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
        data_rows = self._decorate_rows_with_meta(data_rows, headers)
        if not data_rows:
            return None

        table_block: TableBlock = dict(extra_fields or {})
        table_block.update(
            {
                "table_id": table_id,
                "source": source,
                "page": page,
                "headers": headers,
                "header_meta": self._build_header_meta(headers),
                "rows": data_rows,
                "row_count": len(data_rows),
                "col_count": max((len(row.get("cells", [])) for row in data_rows), default=0),
            }
        )
        return table_block
