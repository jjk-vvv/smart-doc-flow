from __future__ import annotations

import re
from typing import Any, Callable, Dict, List


TableBlocks = List[Dict[str, Any]]
NormalizeText = Callable[[str], str]
ContainsSectionMarker = Callable[[str], bool]
HeaderTokenIsGeneric = Callable[[str], bool]


class TablePruningRuntime:
    """Prune low-signal table fragments after OCR / visual extraction stages."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        contains_section_marker: ContainsSectionMarker,
        header_token_is_generic: HeaderTokenIsGeneric,
    ) -> None:
        self._normalize_text = normalize_text
        self._contains_section_marker = contains_section_marker
        self._header_token_is_generic = header_token_is_generic

    def prune_fragment_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks

        robust_by_page: Dict[int, int] = {}
        robust_total = 0
        for table in table_blocks:
            rows = int(table.get("row_count", 0) or 0)
            cols = int(table.get("col_count", 0) or 0)
            if rows >= 2 and cols >= 2:
                robust_total += 1
                page_no = int(table.get("page", 0) or 0)
                if page_no > 0:
                    robust_by_page[page_no] = robust_by_page.get(page_no, 0) + 1

        if robust_total == 0:
            return table_blocks

        pruned: TableBlocks = []
        for table in table_blocks:
            rows = int(table.get("row_count", 0) or 0)
            cols = int(table.get("col_count", 0) or 0)
            page_no = int(table.get("page", 0) or 0)
            source = str(table.get("source", "") or "")
            cells = [
                cell
                for row in table.get("rows", [])
                for cell in row.get("cells", [])
                if isinstance(cell, dict)
            ]
            cell_count = len(cells)
            numeric_cells = sum(1 for cell in cells if re.search(r"\d", str(cell.get("text", ""))))
            same_page_has_robust = robust_by_page.get(page_no, 0) > 0

            if source == "pdf_ocr_layout":
                numeric_ratio = numeric_cells / float(max(cell_count, 1))
                section_cell_hits = sum(
                    1
                    for cell in cells
                    if self._contains_section_marker(str(cell.get("text", "")))
                )
                section_cell_ratio = section_cell_hits / float(max(cell_count, 1))
                headers = [self._normalize_text(str(item or "")) for item in table.get("headers", [])]
                headers = [item for item in headers if item]
                generic_headers = sum(1 for item in headers if self._header_token_is_generic(item))
                generic_ratio = (generic_headers / float(max(len(headers), 1))) if headers else 0.0
                if rows <= 3 and cols <= 3 and numeric_cells < 6:
                    continue
                if rows >= 10 and cols <= 3 and numeric_ratio < 0.45:
                    continue
                if rows >= 10 and cols >= 6 and numeric_ratio < 0.2 and section_cell_ratio >= 0.03:
                    continue
                if rows >= 8 and section_cell_ratio >= 0.04 and numeric_ratio < 0.35:
                    continue
                if generic_ratio >= 0.6 and numeric_ratio < 0.38:
                    continue

            if rows <= 1:
                keep_sparse_row = cols >= 4 and cell_count >= 4 and numeric_cells >= 3 and robust_total <= 1
                if keep_sparse_row and not same_page_has_robust:
                    pruned.append(table)
                continue
            if cols > 1:
                pruned.append(table)
                continue

            keep_long_single_column = rows >= 6 and cell_count >= 6 and numeric_cells >= 2
            keep_gemini_signal = source.startswith("pdf_gemini_vision") and rows >= 3 and cell_count >= 3
            if keep_long_single_column or keep_gemini_signal:
                pruned.append(table)
                continue

            if same_page_has_robust or robust_total >= 2:
                continue

            if numeric_cells >= 2 and rows >= 3:
                pruned.append(table)

        out = pruned if pruned else table_blocks
        out = self.prune_ocr_layout_density(out)
        return self.prune_gemini_native_tables_per_page(out)

    def prune_ocr_layout_density(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(table)

        pruned: TableBlocks = []
        for page_no in sorted(by_page.keys()):
            page_tables = by_page.get(page_no, [])
            non_ocr = [table for table in page_tables if str(table.get("source", "")) != "pdf_ocr_layout"]
            ocr = [table for table in page_tables if str(table.get("source", "")) == "pdf_ocr_layout"]
            pruned.extend(non_ocr)
            if not ocr:
                continue

            candidates: List[Dict[str, Any]] = []
            for table in ocr:
                rows = int(table.get("row_count", 0) or 0)
                cols = int(table.get("col_count", 0) or 0)
                cells = [
                    cell
                    for row in table.get("rows", [])
                    for cell in row.get("cells", [])
                    if isinstance(cell, dict)
                ]
                cell_count = len(cells)
                numeric_cells = sum(
                    1
                    for cell in cells
                    if cell.get("numeric_value") is not None or re.search(r"\d", str(cell.get("text", "")))
                )
                numeric_ratio = numeric_cells / float(max(cell_count, 1))
                if cols <= 2 and numeric_ratio < 0.75:
                    continue
                if cols <= 3 and rows >= 8 and numeric_ratio < 0.65:
                    continue
                if cols <= 4 and rows <= 4 and numeric_ratio < 0.65:
                    continue
                candidates.append(table)

            if not candidates:
                continue
            candidates.sort(
                key=lambda item: (
                    float(item.get("quality", 0.0) or 0.0),
                    int(item.get("row_count", 0) or 0) * int(item.get("col_count", 0) or 0),
                ),
                reverse=True,
            )
            pruned.append(candidates[0])

        pruned.sort(key=lambda item: (int(item.get("page", 0) or 0), str(item.get("table_id", ""))))
        return pruned if pruned else table_blocks

    def prune_gemini_native_tables_per_page(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(table)

        out: TableBlocks = []
        for page_no in sorted(by_page.keys()):
            tables = by_page.get(page_no, [])
            native_vision = [table for table in tables if str(table.get("source", "")) == "pdf_gemini_vision_native"]
            others = [table for table in tables if str(table.get("source", "")) != "pdf_gemini_vision_native"]
            out.extend(others)
            if not native_vision:
                continue
            native_vision.sort(
                key=lambda item: (
                    float(item.get("quality", 0.0) or 0.0),
                    int(item.get("row_count", 0) or 0) * int(item.get("col_count", 0) or 0),
                ),
                reverse=True,
            )
            out.append(native_vision[0])
        return out
