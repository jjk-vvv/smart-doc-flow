from __future__ import annotations

import re
from html import escape
from typing import Any, Callable, Dict, List, Tuple


TableBlocks = List[Dict[str, Any]]
RowsPayload = List[Dict[str, Any]]
PageCells = Dict[int, List[Dict[str, Any]]]
PageLines = Dict[int, List[str]]

InferHeadersAndDataRows = Callable[[RowsPayload], Tuple[List[str], RowsPayload]]
DropRedundantHeaderRows = Callable[[RowsPayload, List[str]], RowsPayload]
DecorateRowsWithMeta = Callable[[RowsPayload, List[str]], RowsPayload]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
BoolTableFilter = Callable[[List[str], RowsPayload], bool]
NormalizeText = Callable[[str], str]
BoolTextFn = Callable[[str], bool]
MergeFn = Callable[[TableBlocks], TableBlocks]
OcrRowsFn = Callable[[List[Dict[str, Any]], float], List[Dict[str, Any]]]
GroupRowsFn = Callable[..., List[List[Dict[str, Any]]]]
SplitGroupByRowGapsFn = Callable[[List[Dict[str, Any]]], List[List[Dict[str, Any]]]]
BuildAnchorsFn = Callable[[List[Dict[str, Any]], float], List[float]]
NearestAnchorFn = Callable[[float, List[float]], int]
ExpandGroupFn = Callable[[List[Dict[str, Any]], List[float], List[Dict[str, Any]]], List[Dict[str, Any]]]
QualityScoreFn = Callable[[List[Dict[str, Any]], List[float]], float]
DedupeCellsFn = Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]
MedianCellHeightFn = Callable[[List[Dict[str, Any]]], float]
SplitTableLineFn = Callable[[str], List[str]]
IsTableLineFn = Callable[[str, List[str]], bool]


class OcrTableInferenceRuntime:
    def __init__(
        self,
        *,
        ocr_table_min_quality: float,
        ocr_table_min_cols: int,
        ocr_table_min_rows: int,
        ocr_table_row_tol: float,
        ocr_table_row_gap: float,
        ocr_table_col_tol: float,
        ocr_table_relaxed_row_gap_scale: float,
        ocr_table_relaxed_align_min: float,
        ocr_table_relaxed_overlap_min: float,
        ocr_table_relaxed_col_diff_max: int,
        table_max_rows: int,
        table_max_cols: int,
        table_cell_cap: int,
        table_merge_enable: bool,
        runtime_page_count_provider: Callable[[], int],
        infer_headers_and_data_rows: InferHeadersAndDataRows,
        drop_redundant_header_like_rows: DropRedundantHeaderRows,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        build_header_meta: BuildHeaderMeta,
        looks_like_false_table: BoolTableFilter,
        normalize_text: NormalizeText,
        contains_section_marker: BoolTextFn,
        is_page_number_token: BoolTextFn,
        dedupe_ocr_cells: DedupeCellsFn,
        median_cell_height: MedianCellHeightFn,
        cluster_ocr_rows: OcrRowsFn,
        group_table_rows: GroupRowsFn,
        split_group_by_row_gaps: SplitGroupByRowGapsFn,
        build_col_anchors: BuildAnchorsFn,
        nearest_anchor_index: NearestAnchorFn,
        expand_group_with_sparse_rows: ExpandGroupFn,
        table_quality_score: QualityScoreFn,
        split_table_line: SplitTableLineFn,
        is_table_line: IsTableLineFn,
        merge_same_page_tables: MergeFn,
        merge_cross_page_tables: MergeFn,
    ) -> None:
        self.ocr_table_min_quality = ocr_table_min_quality
        self.ocr_table_min_cols = ocr_table_min_cols
        self.ocr_table_min_rows = ocr_table_min_rows
        self.ocr_table_row_tol = ocr_table_row_tol
        self.ocr_table_row_gap = ocr_table_row_gap
        self.ocr_table_col_tol = ocr_table_col_tol
        self.ocr_table_relaxed_row_gap_scale = ocr_table_relaxed_row_gap_scale
        self.ocr_table_relaxed_align_min = ocr_table_relaxed_align_min
        self.ocr_table_relaxed_overlap_min = ocr_table_relaxed_overlap_min
        self.ocr_table_relaxed_col_diff_max = ocr_table_relaxed_col_diff_max
        self.table_max_rows = table_max_rows
        self.table_max_cols = table_max_cols
        self.table_cell_cap = table_cell_cap
        self.table_merge_enable = table_merge_enable
        self._runtime_page_count_provider = runtime_page_count_provider
        self._infer_headers_and_data_rows = infer_headers_and_data_rows
        self._drop_redundant_header_like_rows = drop_redundant_header_like_rows
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._build_header_meta = build_header_meta
        self._looks_like_false_table = looks_like_false_table
        self._normalize_text = normalize_text
        self._contains_section_marker = contains_section_marker
        self._is_page_number_token = is_page_number_token
        self._dedupe_ocr_cells = dedupe_ocr_cells
        self._median_cell_height = median_cell_height
        self._cluster_ocr_rows = cluster_ocr_rows
        self._group_table_rows = group_table_rows
        self._split_group_by_row_gaps = split_group_by_row_gaps
        self._build_col_anchors = build_col_anchors
        self._nearest_anchor_index = nearest_anchor_index
        self._expand_group_with_sparse_rows = expand_group_with_sparse_rows
        self._table_quality_score = table_quality_score
        self._split_table_line = split_table_line
        self._is_table_line = is_table_line
        self._merge_same_page_tables = merge_same_page_tables
        self._merge_cross_page_tables = merge_cross_page_tables

    def infer_tables_from_ocr_cells(
        self,
        page_cells: PageCells,
        min_quality: float | None = None,
        enable_relaxed_second_pass: bool = True,
    ) -> TableBlocks:
        table_blocks: TableBlocks = []
        table_idx = 1
        quality_threshold = self.ocr_table_min_quality if min_quality is None else float(min_quality)

        for page_no in sorted(page_cells.keys()):
            raw_cells = [cell for cell in page_cells.get(page_no, []) if cell.get("text")]
            cells = self._dedupe_ocr_cells(raw_cells)
            if len(cells) < self.ocr_table_min_cols * self.ocr_table_min_rows:
                continue

            dynamic_row_tol = max(self.ocr_table_row_tol, self._median_cell_height(cells) * 1.25)
            rows = self._cluster_ocr_rows(cells, dynamic_row_tol)
            candidate_rows = [row for row in rows if len(row.get("cells", [])) >= self.ocr_table_min_cols]
            if len(candidate_rows) < self.ocr_table_min_rows:
                continue

            groups = self._group_table_rows(candidate_rows)
            page_tables, table_idx = self.build_tables_from_row_groups(
                page_no=page_no,
                groups=groups,
                quality_threshold=quality_threshold,
                table_idx=table_idx,
                all_rows=rows,
            )

            if (
                enable_relaxed_second_pass
                and not page_tables
                and len(candidate_rows) >= (self.ocr_table_min_rows + 1)
                and len(candidate_rows) <= 48
                and len(cells) <= 420
            ):
                relaxed_groups = self._group_table_rows(
                    candidate_rows,
                    row_gap=self.ocr_table_row_gap * self.ocr_table_relaxed_row_gap_scale,
                    align_min=self.ocr_table_relaxed_align_min,
                    overlap_min=self.ocr_table_relaxed_overlap_min,
                    col_diff_max=self.ocr_table_relaxed_col_diff_max,
                )
                page_tables, table_idx = self.build_tables_from_row_groups(
                    page_no=page_no,
                    groups=relaxed_groups,
                    quality_threshold=quality_threshold,
                    table_idx=table_idx,
                    all_rows=rows,
                )
            table_blocks.extend(page_tables)

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    def build_tables_from_row_groups(
        self,
        *,
        page_no: int,
        groups: List[List[Dict[str, Any]]],
        quality_threshold: float,
        table_idx: int,
        all_rows: List[Dict[str, Any]] | None = None,
    ) -> Tuple[TableBlocks, int]:
        page_tables: TableBlocks = []
        for raw_group in groups:
            for group in self._split_group_by_row_gaps(raw_group):
                if len(group) < self.ocr_table_min_rows:
                    continue

                anchors = self._build_col_anchors(group, self.ocr_table_col_tol)
                if len(anchors) < self.ocr_table_min_cols:
                    continue
                base_quality = self._table_quality_score(group, anchors)
                if base_quality < quality_threshold:
                    continue

                use_group = group
                quality = base_quality
                if base_quality >= max(quality_threshold + 0.06, 0.62):
                    dense_group = self._expand_group_with_sparse_rows(group, anchors, all_rows or group)
                    if len(dense_group) > len(group):
                        dense_quality = self._table_quality_score(dense_group, anchors)
                        added_rows = len(dense_group) - len(group)
                        max_added = max(2, min(6, (len(group) // 2) + 1))
                        if added_rows <= max_added and dense_quality >= quality_threshold and dense_quality + 0.03 >= base_quality:
                            use_group = dense_group
                            quality = dense_quality
                if quality < quality_threshold:
                    continue

                rows_payload = self._build_rows_payload(page_no=page_no, group=use_group, anchors=anchors)
                if len(rows_payload) < self.ocr_table_min_rows:
                    continue

                headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
                data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
                data_rows = self._decorate_rows_with_meta(data_rows, headers)
                if len(data_rows) < self.ocr_table_min_rows and not self._allow_single_row_layout_table(data_rows):
                    continue
                if self._looks_like_false_table(headers, data_rows):
                    continue

                col_count = max((len(row.get("cells", [])) for row in data_rows), default=0)
                if self._should_skip_sparse_layout_table(data_rows, col_count):
                    continue

                page_tables.append(
                    {
                        "table_id": f"pdf_ocr_layout_t{table_idx}",
                        "source": "pdf_ocr_layout",
                        "page": page_no,
                        "headers": headers,
                        "header_meta": self._build_header_meta(headers),
                        "rows": data_rows,
                        "row_count": len(data_rows),
                        "col_count": col_count,
                        "quality": round(quality, 4),
                    }
                )
                table_idx += 1
        return page_tables, table_idx

    def infer_tables_from_page_lines(
        self,
        page_lines: PageLines,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source: str,
    ) -> TableBlocks:
        table_blocks: TableBlocks = []
        table_idx = 1
        emitted_cells = 0

        for page_no in sorted(page_lines.keys()):
            lines = page_lines.get(page_no, [])
            groups: List[List[List[str]]] = []
            current_group: List[List[str]] = []

            for line in lines:
                tokens = self._split_table_line(line)
                if self._is_table_line(line, tokens):
                    current_group.append(tokens)
                else:
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = []
            if len(current_group) >= 2:
                groups.append(current_group)

            for group in groups:
                if emitted_cells >= self.table_cell_cap:
                    break
                raw_rows = group[: self.table_max_rows + 1]
                if len(raw_rows) < self.ocr_table_min_rows:
                    continue

                table_id = f"{source}_t{table_idx}"
                raw_rows_payload: RowsPayload = []
                for row_idx, row_tokens in enumerate(raw_rows, start=1):
                    cells_payload: List[Dict[str, Any]] = []
                    for col_idx, text in enumerate(row_tokens[: self.table_max_cols], start=1):
                        normalized = self._normalize_text(text)
                        if not normalized:
                            continue
                        ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
                        bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                        bbox_map[ref_id] = bbox
                        cells_payload.append(
                            {
                                "col_index": col_idx,
                                "text": normalized,
                                "ref_id": ref_id,
                                "bbox": bbox,
                            }
                        )
                        emitted_cells += 1
                        if emitted_cells >= self.table_cell_cap:
                            break
                    if cells_payload:
                        raw_rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                    if emitted_cells >= self.table_cell_cap:
                        break

                if raw_rows_payload:
                    headers, data_rows_payload = self._infer_headers_and_data_rows(raw_rows_payload)
                    data_rows_payload = self._drop_redundant_header_like_rows(data_rows_payload, headers)
                    data_rows_payload = self._decorate_rows_with_meta(data_rows_payload, headers)
                    if len(data_rows_payload) < self.ocr_table_min_rows and not self._allow_single_row_line_table(data_rows_payload):
                        continue
                    if self._looks_like_false_table(headers, data_rows_payload):
                        continue
                    table_blocks.append(
                        {
                            "table_id": table_id,
                            "source": source,
                            "page": page_no,
                            "headers": headers,
                            "header_meta": self._build_header_meta(headers),
                            "rows": data_rows_payload,
                            "row_count": len(data_rows_payload),
                            "col_count": max((len(row.get("cells", [])) for row in data_rows_payload), default=0),
                        }
                    )
                    table_idx += 1

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    def _build_rows_payload(
        self,
        *,
        page_no: int,
        group: List[Dict[str, Any]],
        anchors: List[float],
    ) -> RowsPayload:
        rows_payload: RowsPayload = []
        for row_idx, row in enumerate(group[: self.table_max_rows], start=1):
            row_cells = sorted(row.get("cells", []), key=lambda cell: cell.get("x_center", 0.0))
            row_map: Dict[int, Dict[str, Any]] = {}
            for cell in row_cells:
                col_index = self._nearest_anchor_index(cell.get("x_center", 0.0), anchors) + 1
                if col_index in row_map:
                    prev = row_map[col_index]
                    if len(str(cell.get("text", ""))) > len(str(prev.get("text", ""))):
                        row_map[col_index] = cell
                else:
                    row_map[col_index] = cell

            cells_payload: List[Dict[str, Any]] = []
            for col_index in sorted(row_map.keys())[: self.table_max_cols]:
                cell = row_map[col_index]
                cells_payload.append(
                    {
                        "col_index": col_index,
                        "text": str(cell.get("text", "")).strip(),
                        "ref_id": cell.get("ref_id"),
                        "bbox": cell.get("bbox", [float(page_no), 0.0, 0.0, 1.0, 1.0]),
                    }
                )
            if cells_payload:
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})
        return rows_payload

    def _allow_single_row_layout_table(self, data_rows: RowsPayload) -> bool:
        return (
            len(data_rows) == 1
            and int(self._runtime_page_count_provider() or 0) <= 120
            and len(data_rows[0].get("cells", [])) >= 3
            and sum(
                1
                for cell in data_rows[0].get("cells", [])
                if cell.get("numeric_value") is not None or re.search(r"\d", str(cell.get("text", "")))
            )
            >= 2
        )

    def _allow_single_row_line_table(self, data_rows: RowsPayload) -> bool:
        if len(data_rows) != 1:
            return False
        first_cells = data_rows[0].get("cells", [])
        numeric_hits = sum(
            1
            for cell in first_cells
            if cell.get("numeric_value") is not None or re.search(r"\d", str(cell.get("text", "")))
        )
        return len(first_cells) >= 3 and numeric_hits >= 2

    def _should_skip_sparse_layout_table(self, data_rows: RowsPayload, col_count: int) -> bool:
        numeric_dense_rows = 0
        section_like_rows = 0
        edge_page_rows = 0
        for row in data_rows[:80]:
            cells = row.get("cells", [])
            numeric_hits = sum(
                1
                for cell in cells
                if cell.get("numeric_value") is not None or re.search(r"\d", str(cell.get("text", "")))
            )
            if numeric_hits >= 2:
                numeric_dense_rows += 1
            row_values = [self._normalize_text(str(cell.get("text", ""))) for cell in cells if cell.get("text")]
            row_text = " ".join(row_values)
            if self._contains_section_marker(row_text):
                section_like_rows += 1
            if row_values and (
                self._is_page_number_token(row_values[0]) or self._is_page_number_token(row_values[-1])
            ):
                edge_page_rows += 1

        sample_size = float(max(len(data_rows[:80]), 1))
        section_ratio = section_like_rows / sample_size
        edge_page_ratio = edge_page_rows / sample_size

        if col_count <= 2 and len(data_rows) <= 3 and numeric_dense_rows < 2:
            return True
        if col_count <= 3 and len(data_rows) >= 8 and numeric_dense_rows < 2:
            return True
        if col_count <= 3 and len(data_rows) >= 8 and section_ratio >= 0.18 and edge_page_ratio >= 0.35:
            return True
        if col_count <= 3 and len(data_rows) >= 12 and edge_page_ratio >= 0.45 and numeric_dense_rows < 4:
            return True
        if col_count <= 3 and len(data_rows) >= 12 and section_ratio >= 0.2 and numeric_dense_rows < 3:
            return True
        return False
