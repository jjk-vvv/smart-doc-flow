from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Tuple

try:
    from app.modules.module2.core.format.plain_text_parser import normalize_text
except ModuleNotFoundError:
    def normalize_text(text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

try:
    from app.modules.module2.core.table.table_metadata import normalize_token_for_compare
except ModuleNotFoundError:
    def normalize_token_for_compare(text: str) -> str:
        token = str(text or "").strip().lower()
        token = re.sub(r"[\s\(\)\[\]{}<>/\\,.;:：，、\-_]+", "", token)
        return token


TableBlocks = List[Dict[str, Any]]
PageLines = Dict[int, List[str]]
TableMergeFn = Callable[[TableBlocks], TableBlocks]
CueTextFn = Callable[[str], bool]


class OcrTableUtils:
    def __init__(
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
        looks_like_table_cue_text: CueTextFn,
        merge_same_page_tables: TableMergeFn,
        merge_cross_page_tables: TableMergeFn,
    ) -> None:
        self.ocr_max_pages = ocr_max_pages
        self.ocr_front_scan_pages = ocr_front_scan_pages
        self.ocr_extra_sample_pages = ocr_extra_sample_pages
        self.ocr_cue_neighbor = ocr_cue_neighbor
        self.ocr_cue_max_pages = ocr_cue_max_pages
        self.ocr_max_scan_pages = ocr_max_scan_pages
        self.ocr_cue_boost_max_pages = ocr_cue_boost_max_pages
        self.ocr_min_coverage_ratio = ocr_min_coverage_ratio
        self.ocr_min_scan_pages = ocr_min_scan_pages
        self.visual_weak_table_min = visual_weak_table_min
        self.ocr_table_min_quality = ocr_table_min_quality
        self.ocr_line_aug_max_extra_cue_pages = ocr_line_aug_max_extra_cue_pages
        self.ocr_uncovered_line_aug_pages = ocr_uncovered_line_aug_pages
        self.table_merge_enable = table_merge_enable
        self.ocr_table_min_rows = ocr_table_min_rows
        self.ocr_table_row_gap = ocr_table_row_gap
        self.ocr_table_col_tol = ocr_table_col_tol
        self._looks_like_table_cue_text = looks_like_table_cue_text
        self._merge_same_page_tables = merge_same_page_tables
        self._merge_cross_page_tables = merge_cross_page_tables

    @staticmethod
    def _even_sample(source: List[int], n: int) -> List[int]:
        if n <= 0 or not source:
            return []
        if n >= len(source):
            return source[:]
        if n == 1:
            return [source[len(source) // 2]]
        step = (len(source) - 1) / float(n - 1)
        picked = [source[int(round(i * step))] for i in range(n)]
        seen_local = set()
        out_local: List[int] = []
        for idx_local in picked:
            if idx_local in seen_local:
                continue
            seen_local.add(idx_local)
            out_local.append(idx_local)
        if len(out_local) < n:
            for idx_local in source:
                if idx_local in seen_local:
                    continue
                seen_local.add(idx_local)
                out_local.append(idx_local)
                if len(out_local) >= n:
                    break
        return out_local

    @staticmethod
    def _interleave_edges(source: List[int]) -> List[int]:
        if not source:
            return []
        out_local: List[int] = []
        left = 0
        right = len(source) - 1
        while left <= right:
            out_local.append(source[left])
            left += 1
            if left <= right:
                out_local.append(source[right])
                right -= 1
        return out_local

    def build_ocr_page_indices(self, page_count: int, cue_pages: List[int] | None = None) -> List[int]:
        if page_count <= 0:
            return []

        first_span = min(page_count, self.ocr_max_pages)
        if not cue_pages and self.ocr_front_scan_pages > first_span:
            first_span = min(page_count, self.ocr_front_scan_pages)
        first_indices: List[int] = list(range(first_span))
        base_extra_indices: List[int] = []
        remaining = list(range(first_span, page_count))
        if remaining and self.ocr_extra_sample_pages > 0:
            extra = min(len(remaining), self.ocr_extra_sample_pages)
            base_extra_indices = self._even_sample(remaining, extra)
        base_indices: List[int] = first_indices + base_extra_indices

        cue_indices: List[int] = []
        if cue_pages:
            valid_cues = sorted(set(int(p) for p in cue_pages if isinstance(p, int) and 0 <= int(p) < page_count))
            expanded: List[int] = []
            for page_idx in valid_cues:
                for delta in range(-self.ocr_cue_neighbor, self.ocr_cue_neighbor + 1):
                    cur = page_idx + delta
                    if 0 <= cur < page_count:
                        expanded.append(cur)
            cue_indices = sorted(set(expanded))
            if self.ocr_cue_max_pages > 0 and len(cue_indices) > self.ocr_cue_max_pages:
                cue_indices = sorted(self._even_sample(cue_indices, self.ocr_cue_max_pages))

        hard_cap_base = min(page_count, self.ocr_max_scan_pages)
        if cue_indices:
            cue_cap = min(page_count, self.ocr_cue_boost_max_pages, max(first_span, len(cue_indices)))
            hard_cap = max(hard_cap_base, cue_cap)
        else:
            hard_cap = hard_cap_base
        target_by_ratio = int(round(page_count * self.ocr_min_coverage_ratio))
        target = max(len(base_indices), self.ocr_min_scan_pages, target_by_ratio)
        target = min(hard_cap, target)

        selected_set = set(i for i in (base_indices + cue_indices) if 0 <= i < page_count)
        if len(selected_set) < target:
            universe = [i for i in range(page_count) if i not in selected_set]
            for idx_local in self._even_sample(universe, target - len(selected_set)):
                selected_set.add(idx_local)

        mandatory: List[int] = []
        mandatory_seen = set()
        for idx_local in first_indices + cue_indices + base_extra_indices:
            if idx_local in selected_set and idx_local not in mandatory_seen:
                mandatory.append(idx_local)
                mandatory_seen.add(idx_local)

        if len(selected_set) > hard_cap:
            if len(mandatory) > hard_cap:
                mandatory = self._even_sample(mandatory, hard_cap)
                mandatory_seen = set(mandatory)
            rest = sorted(i for i in selected_set if i not in mandatory_seen)
            slots = max(0, hard_cap - len(mandatory))
            trimmed = set(mandatory)
            for idx_local in self._even_sample(rest, slots):
                trimmed.add(idx_local)
            selected_set = trimmed

        ordered: List[int] = []
        seen = set()

        def _append(idx_local: int) -> None:
            if idx_local in selected_set and idx_local not in seen:
                ordered.append(idx_local)
                seen.add(idx_local)

        for idx_local in mandatory:
            _append(idx_local)

        remaining_sorted = sorted(i for i in selected_set if i not in seen)
        if remaining_sorted:
            anchor_n = min(len(remaining_sorted), max(6, min(24, target // 2 if target > 0 else 6)))
            anchors = self._even_sample(remaining_sorted, anchor_n)
            for idx_local in self._interleave_edges(anchors):
                _append(idx_local)
            for idx_local in self._interleave_edges(remaining_sorted):
                _append(idx_local)

        return ordered

    def need_line_table_augmentation(self, table_blocks: TableBlocks, page_lines: PageLines) -> bool:
        if not page_lines:
            return False
        if not table_blocks:
            return True
        if len(table_blocks) < self.visual_weak_table_min:
            return True

        quality_vals: List[float] = []
        for table in table_blocks:
            try:
                quality_vals.append(float(table.get("quality")))
            except (TypeError, ValueError):
                continue
        if not quality_vals:
            return True

        avg_q = sum(quality_vals) / float(max(len(quality_vals), 1))
        low_q = sum(1 for value in quality_vals if value < max(self.ocr_table_min_quality + 0.08, 0.72))
        low_ratio = low_q / float(max(len(quality_vals), 1))
        return avg_q < 0.8 and low_ratio >= 0.34

    def select_line_augmentation_pages(
        self,
        page_lines: PageLines,
        base_tables: TableBlocks,
        cue_pages: List[int] | None = None,
    ) -> PageLines:
        if not page_lines:
            return {}
        if not base_tables:
            return page_lines

        focus_pages = set()
        for table in base_tables:
            page_no = int(table.get("page", 0) or 0)
            if page_no <= 0:
                continue
            focus_pages.add(page_no)
            focus_pages.add(page_no - 1)
            focus_pages.add(page_no + 1)

        cue_candidates = sorted(
            {
                int(page_idx) + 1
                for page_idx in (cue_pages or [])
                if isinstance(page_idx, int) and (int(page_idx) + 1) in page_lines
            }
        )
        if cue_candidates and self.ocr_line_aug_max_extra_cue_pages > 0:
            if len(cue_candidates) > self.ocr_line_aug_max_extra_cue_pages:
                step = (len(cue_candidates) - 1) / float(max(self.ocr_line_aug_max_extra_cue_pages - 1, 1))
                cue_candidates = sorted(
                    {
                        cue_candidates[int(round(i * step))]
                        for i in range(self.ocr_line_aug_max_extra_cue_pages)
                    }
                )
            for page_no in cue_candidates:
                focus_pages.add(page_no)

        cue_text_pages = [
            page_no
            for page_no, lines in page_lines.items()
            if self._looks_like_table_cue_text(" ".join(lines[:18]))
        ]
        if cue_text_pages and self.ocr_line_aug_max_extra_cue_pages > 0:
            if len(cue_text_pages) > self.ocr_line_aug_max_extra_cue_pages:
                step = (len(cue_text_pages) - 1) / float(max(self.ocr_line_aug_max_extra_cue_pages - 1, 1))
                cue_text_pages = sorted(
                    {
                        cue_text_pages[int(round(i * step))]
                        for i in range(self.ocr_line_aug_max_extra_cue_pages)
                    }
                )
            for page_no in cue_text_pages:
                focus_pages.add(page_no)

        valid = sorted(page_no for page_no in focus_pages if page_no in page_lines)
        if not valid:
            return page_lines

        hard_limit = max(18, min(64, self.ocr_max_scan_pages // 2))
        if len(valid) <= hard_limit:
            return {page_no: page_lines[page_no] for page_no in valid}

        step = (len(valid) - 1) / float(max(hard_limit - 1, 1))
        sampled = [valid[int(round(i * step))] for i in range(hard_limit)]
        return {page_no: page_lines[page_no] for page_no in sorted(set(sampled))}

    def select_uncovered_table_like_pages(
        self,
        page_lines: PageLines,
        base_tables: TableBlocks,
        aggressive: bool = False,
    ) -> PageLines:
        if not page_lines or not base_tables or self.ocr_uncovered_line_aug_pages <= 0:
            return {}
        covered_pages = {
            int(table.get("page", 0) or 0)
            for table in base_tables
            if int(table.get("page", 0) or 0) > 0
        }
        total_page_count = max(len(page_lines), 1)
        coverage_ratio = len(covered_pages) / float(total_page_count)
        min_table_line_hits = 2 if aggressive else 3
        min_numeric_line_hits = 1 if aggressive else 2
        min_score = 6 if aggressive else 9
        if coverage_ratio < 0.22:
            min_score = max(5 if aggressive else 8, min_score - 1)
        max_pages = self.ocr_uncovered_line_aug_pages + (4 if aggressive else 0)
        if coverage_ratio < 0.22:
            max_pages += 2
        if aggressive and total_page_count >= 80:
            max_pages += min(6, total_page_count // 40)
        max_pages = max(
            self.ocr_uncovered_line_aug_pages,
            min(max_pages, max(12, self.ocr_uncovered_line_aug_pages * 3)),
        )
        candidates: List[Tuple[int, int]] = []
        for page_no, lines in page_lines.items():
            if page_no in covered_pages or not lines:
                continue

            score = 0
            if self._looks_like_table_cue_text(" ".join(lines[:24])):
                score += 2
            if (page_no - 1) in covered_pages or (page_no + 1) in covered_pages:
                score += 2
            if re.search(r"\btable\b|^\s*\u8868\s*[0-9A-Za-z\u4e00-\u9fa5.\-]*", " ".join(lines[:20]), re.IGNORECASE):
                score += 2

            table_line_hits = 0
            numeric_line_hits = 0
            for line in lines[:160]:
                tokens = self.split_table_line(line)
                if not self.is_table_line(line, tokens):
                    continue
                table_line_hits += 1
                score += 1
                numeric_hits = sum(1 for token in tokens if re.search(r"\d", token))
                if numeric_hits >= 2:
                    numeric_line_hits += 1
                    score += 1
                if len(tokens) >= 5:
                    score += 1
            if table_line_hits >= min_table_line_hits and numeric_line_hits >= min_numeric_line_hits and score >= min_score:
                candidates.append((score, page_no))

        if not candidates:
            return {}
        chosen = [page for _, page in sorted(candidates, key=lambda item: (-item[0], item[1]))[:max_pages]]
        return {page_no: page_lines[page_no] for page_no in sorted(chosen)}

    def table_signature(self, table: Dict[str, Any]) -> str:
        page_no = int(table.get("page", 0) or 0)
        headers = [normalize_token_for_compare(str(header or "")) for header in table.get("headers", [])]
        headers = [header for header in headers if header][:6]
        col_count = int(table.get("col_count", 0) or 0)
        row_count = int(table.get("row_count", 0) or 0)
        first_row_tokens: List[str] = []
        rows = table.get("rows", [])
        if isinstance(rows, list) and rows:
            first_cells = rows[0].get("cells", []) if isinstance(rows[0], dict) else []
            if isinstance(first_cells, list):
                for cell in first_cells[:6]:
                    first_row_tokens.append(normalize_token_for_compare(str(cell.get("text", ""))))
        first_row_tokens = [token for token in first_row_tokens if token]
        return "|".join(
            [
                str(page_no),
                str(col_count),
                str(row_count),
                ",".join(headers),
                ",".join(first_row_tokens),
            ]
        )

    def augment_with_line_tables(self, base_tables: TableBlocks, line_tables: TableBlocks) -> TableBlocks:
        if not base_tables:
            return line_tables
        if not line_tables:
            return base_tables

        out: TableBlocks = list(base_tables)
        seen = {self.table_signature(table) for table in base_tables}
        for table in line_tables:
            signature = self.table_signature(table)
            if not signature or signature in seen:
                continue
            rows = int(table.get("row_count", 0) or 0)
            cols = int(table.get("col_count", 0) or 0)
            if rows <= 1 or cols <= 1:
                continue
            out.append(table)
            seen.add(signature)

        if out and self.table_merge_enable:
            out = self._merge_same_page_tables(out)
            out = self._merge_cross_page_tables(out)
        return out

    def split_group_by_row_gaps(self, group: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        if len(group) < (self.ocr_table_min_rows * 2):
            return [group]
        ordered = sorted(group, key=lambda row: float(row.get("y_center", 0.0)))
        gaps: List[float] = []
        col_counts = [len(row.get("cells", [])) for row in ordered]
        for idx in range(1, len(ordered)):
            gaps.append(float(ordered[idx].get("y_center", 0.0)) - float(ordered[idx - 1].get("y_center", 0.0)))
        if not gaps:
            return [ordered]
        sorted_gaps = sorted(gaps)
        mid = len(sorted_gaps) // 2
        median_gap = sorted_gaps[mid] if len(sorted_gaps) % 2 else (sorted_gaps[mid - 1] + sorted_gaps[mid]) / 2.0
        split_threshold = max(self.ocr_table_row_gap * 1.8, median_gap * 2.7)

        parts: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = [ordered[0]]
        for idx in range(1, len(ordered)):
            gap = gaps[idx - 1]
            prev_cols = col_counts[idx - 1]
            curr_cols = col_counts[idx]
            col_jump = abs(curr_cols - prev_cols)
            should_split = gap > split_threshold
            if not should_split and gap > (self.ocr_table_row_gap * 1.15) and col_jump >= 3:
                should_split = True
            if should_split and len(current) >= self.ocr_table_min_rows:
                parts.append(current)
                current = [ordered[idx]]
            else:
                current.append(ordered[idx])
        if current:
            parts.append(current)

        valid = [part for part in parts if len(part) >= self.ocr_table_min_rows]
        if not valid or len(valid) == 1:
            return [ordered]
        return valid

    def expand_group_with_sparse_rows(
        self,
        group: List[Dict[str, Any]],
        anchors: List[float],
        all_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not group or not all_rows or len(all_rows) > 220:
            return group
        group_ids = {id(row) for row in group}
        ys = [float(row.get("y_center", 0.0)) for row in group]
        y_min = min(ys)
        y_max = max(ys)
        y_pad = self.ocr_table_row_gap * 1.0

        group_cells: List[Dict[str, Any]] = []
        for row in group:
            group_cells.extend(row.get("cells", []))
        g_x0, g_x1 = self.cells_x_span(group_cells)

        selected: List[Dict[str, Any]] = list(group)
        for row in all_rows:
            if id(row) in group_ids:
                continue
            cells = row.get("cells", [])
            if not cells:
                continue
            y = float(row.get("y_center", 0.0))
            if y < (y_min - y_pad) or y > (y_max + y_pad):
                continue
            align = self.row_anchor_coverage(cells, anchors, self.ocr_table_col_tol * 1.25)
            overlap = self.cells_span_overlap(cells, g_x0, g_x1)
            has_numeric = any(re.search(r"\d", str(cell.get("text", ""))) for cell in cells)
            if align >= 0.5 or (len(cells) >= 2 and overlap >= 0.52) or (has_numeric and align >= 0.4 and overlap >= 0.35):
                selected.append(row)

        return sorted(selected, key=lambda row: float(row.get("y_center", 0.0)))

    @staticmethod
    def cluster_ocr_rows(cells: List[Dict[str, Any]], row_tol: float) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        ordered = sorted(cells, key=lambda cell: (cell.get("y_center", 0.0), cell.get("x_center", 0.0)))
        for cell in ordered:
            y = float(cell.get("y_center", 0.0))
            placed = False
            for row in rows:
                if abs(y - row["y_center"]) <= row_tol:
                    row["cells"].append(cell)
                    count = len(row["cells"])
                    row["y_center"] = ((row["y_center"] * (count - 1)) + y) / count
                    placed = True
                    break
            if not placed:
                rows.append({"y_center": y, "cells": [cell]})

        rows.sort(key=lambda row: row["y_center"])
        for row in rows:
            row["cells"] = sorted(row["cells"], key=lambda cell: cell.get("x_center", 0.0))
        return rows

    def group_table_rows(
        self,
        rows: List[Dict[str, Any]],
        row_gap: float | None = None,
        align_min: float = 0.5,
        overlap_min: float = 0.45,
        col_diff_max: int = 1,
    ) -> List[List[Dict[str, Any]]]:
        groups: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        gap_limit = float(self.ocr_table_row_gap if row_gap is None else row_gap)

        for row in rows:
            if not current:
                current = [row]
                continue

            prev = current[-1]
            y_gap = float(row.get("y_center", 0.0)) - float(prev.get("y_center", 0.0))
            align = self.row_alignment_score(prev.get("cells", []), row.get("cells", []), self.ocr_table_col_tol)
            overlap = self.x_overlap_ratio(prev.get("cells", []), row.get("cells", []))
            col_diff = abs(len(prev.get("cells", [])) - len(row.get("cells", [])))

            if y_gap <= gap_limit and ((align >= align_min and overlap >= overlap_min) or col_diff <= col_diff_max):
                current.append(row)
            else:
                if len(current) >= self.ocr_table_min_rows:
                    groups.append(current)
                current = [row]

        if len(current) >= self.ocr_table_min_rows:
            groups.append(current)
        return groups

    @staticmethod
    def row_alignment_score(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]], tol: float) -> float:
        if not cells_a or not cells_b:
            return 0.0
        xs_a = sorted(float(cell.get("x_center", 0.0)) for cell in cells_a)
        xs_b = sorted(float(cell.get("x_center", 0.0)) for cell in cells_b)
        short, long = (xs_a, xs_b) if len(xs_a) <= len(xs_b) else (xs_b, xs_a)
        if not short:
            return 0.0
        matched = 0
        for x in short:
            if any(abs(x - y) <= tol for y in long):
                matched += 1
        return matched / float(len(short))

    @staticmethod
    def x_overlap_ratio(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]]) -> float:
        if not cells_a or not cells_b:
            return 0.0

        def span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
            x0 = min(float(cell.get("bbox", [0, 0, 0, 0, 0])[1]) for cell in cells)
            x1 = max(
                float(cell.get("bbox", [0, 0, 0, 0, 0])[1]) + float(cell.get("bbox", [0, 0, 0, 0, 0])[3])
                for cell in cells
            )
            return x0, x1

        a0, a1 = span(cells_a)
        b0, b1 = span(cells_b)
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        den = max(a1 - a0, b1 - b0, 1e-6)
        return inter / den

    @staticmethod
    def cells_x_span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
        if not cells:
            return 0.0, 1.0
        x0 = min(float(cell.get("bbox", [0, 0, 0, 0, 0])[1]) for cell in cells)
        x1 = max(
            float(cell.get("bbox", [0, 0, 0, 0, 0])[1]) + float(cell.get("bbox", [0, 0, 0, 0, 0])[3])
            for cell in cells
        )
        if x1 <= x0:
            return 0.0, 1.0
        return x0, x1

    @classmethod
    def cells_span_overlap(cls, cells: List[Dict[str, Any]], x0: float, x1: float) -> float:
        if not cells:
            return 0.0
        c0, c1 = cls.cells_x_span(cells)
        inter = max(0.0, min(c1, x1) - max(c0, x0))
        den = max(c1 - c0, x1 - x0, 1e-6)
        return inter / den

    @staticmethod
    def row_anchor_coverage(cells: List[Dict[str, Any]], anchors: List[float], tol: float) -> float:
        if not cells or not anchors:
            return 0.0
        matched = 0
        for cell in cells:
            x = float(cell.get("x_center", 0.0))
            if any(abs(x - anchor) <= tol for anchor in anchors):
                matched += 1
        return matched / float(max(len(cells), 1))

    @staticmethod
    def median_cell_height(cells: List[Dict[str, Any]]) -> float:
        heights = [float(cell.get("bbox", [0, 0, 0, 0, 0])[4]) for cell in cells if len(cell.get("bbox", [])) >= 5]
        heights = [height for height in heights if height > 0]
        if not heights:
            return 0.015
        heights.sort()
        mid = len(heights) // 2
        if len(heights) % 2:
            return heights[mid]
        return (heights[mid - 1] + heights[mid]) / 2.0

    @staticmethod
    def is_page_number_token(text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        if re.fullmatch(r"[\(\[]?\d{1,4}[\)\]]?", token):
            return True
        return bool(re.fullmatch(r"[\(\[]?[ivxlcdm]{1,8}[\)\]]?", token, re.IGNORECASE))

    @staticmethod
    def contains_section_marker(text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        if re.search(r"\u7b2c.{0,4}[\u7ae0\u8282\u7bc7]", token):
            return True
        if "\u6838\u71c3\u6599\u540e\u5904\u7406\u5de5\u5b66" in token:
            return True
        lower = token.lower()
        return bool(re.search(r"\bchapter\b|\bsection\b|\bcontents\b|table of contents|references", lower))

    @staticmethod
    def contains_equation_marker(text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        if re.search(r"\(\d+\-\d+\)", token):
            return True
        return ("=" in token and "+" in token) or ("\u2192" in token) or ("->" in token)

    @staticmethod
    def contains_catalog_marker(text: str) -> bool:
        token = str(text or "").strip().lower()
        if not token:
            return False
        return "list of tables" in token or "table of contents" in token or "contents" == token

    @staticmethod
    def contains_figure_marker(text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        lower = token.lower()
        if re.search(r"\bfig(?:ure)?\.?\s*\d+", lower):
            return True
        if re.search(r"^\s*图\s*[0-9A-Za-z一二三四五六七八九十.\-]+", token):
            return True
        return bool(re.search(r"[\s(（]图\s*[0-9A-Za-z一二三四五六七八九十.\-]+", token))

    @staticmethod
    def contains_table_marker(text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return False
        lower = token.lower()
        if re.search(r"\btable\.?\s*\d+", lower):
            return True
        if re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]+", token):
            return True
        return bool(re.search(r"[\s(（]表\s*[0-9A-Za-z一二三四五六七八九十.\-]+", token))

    @staticmethod
    def is_sentence_like_text(text: str) -> bool:
        token = str(text or "").strip()
        if len(token) < 24:
            return False
        if re.search(r"[。；！？]|[A-Za-z]{3,}\s+[A-Za-z]{3,}", token):
            return True
        return token.count(",") + token.count("，") + token.count(";") + token.count("；") >= 2

    def looks_like_false_table(
        self,
        headers: List[str],
        data_rows: List[Dict[str, Any]],
        *,
        runtime_page_count: int = 0,
    ) -> bool:
        if not headers or not data_rows:
            return True

        cleaned_headers = [normalize_text(str(header or "")) for header in headers if str(header or "").strip()]
        if not cleaned_headers:
            return True

        chapter_hits = sum(1 for header in cleaned_headers if self.contains_section_marker(header))
        catalog_hits = sum(1 for header in cleaned_headers if self.contains_catalog_marker(header))
        page_hits = sum(1 for header in cleaned_headers if self.is_page_number_token(header))
        equation_hits = sum(1 for header in cleaned_headers if self.contains_equation_marker(header))
        figure_hits = sum(1 for header in cleaned_headers if self.contains_figure_marker(header))

        flat_cells: List[Dict[str, Any]] = []
        for row in data_rows:
            for cell in row.get("cells", []):
                flat_cells.append(cell)
                if len(flat_cells) >= 500:
                    break
            if len(flat_cells) >= 500:
                break
        if not flat_cells:
            return True

        numeric_cells = 0
        long_text_cells = 0
        sentence_like_rows = 0
        inspected_rows = 0
        for row in data_rows[:40]:
            cells = row.get("cells", [])
            if not cells:
                continue
            row_text = " ".join(normalize_text(str(cell.get("text", ""))) for cell in cells if cell.get("text"))
            inspected_rows += 1
            if len(cells) <= 2 and self.is_sentence_like_text(row_text):
                sentence_like_rows += 1
        for cell in flat_cells:
            text = normalize_text(str(cell.get("text", "")))
            if not text:
                continue
            if cell.get("numeric_value") is not None or re.search(r"\d", text):
                numeric_cells += 1
            if len(text) >= 24:
                long_text_cells += 1

        total = max(len(flat_cells), 1)
        numeric_ratio = numeric_cells / float(total)
        long_ratio = long_text_cells / float(total)
        sentence_like_ratio = sentence_like_rows / float(max(inspected_rows, 1)) if inspected_rows > 0 else 0.0
        avg_cols = (
            sum(len(row.get("cells", [])) for row in data_rows) / float(max(len(data_rows), 1))
            if data_rows
            else 0.0
        )
        row_end_page_hits = 0
        section_row_hits = 0
        catalog_row_hits = 0
        inspected_toc_rows = 0
        for row in data_rows[:100]:
            cells = sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
            vals = [normalize_text(str(cell.get("text", ""))) for cell in cells if cell.get("text")]
            if not vals:
                continue
            inspected_toc_rows += 1
            if self.is_page_number_token(vals[-1]) or self.is_page_number_token(vals[0]):
                row_end_page_hits += 1
            if any(self.contains_section_marker(value) for value in vals[:2]):
                section_row_hits += 1
            if self.contains_catalog_marker(" ".join(vals)):
                catalog_row_hits += 1
        row_end_page_ratio = row_end_page_hits / float(max(inspected_toc_rows, 1))
        section_row_ratio = section_row_hits / float(max(inspected_toc_rows, 1))
        catalog_row_ratio = catalog_row_hits / float(max(inspected_toc_rows, 1))

        if len(data_rows) >= 14 and avg_cols >= 3.2 and sentence_like_ratio <= 0.45:
            return False
        if len(data_rows) >= 8 and avg_cols <= 3.4 and row_end_page_ratio >= 0.55 and section_row_ratio >= 0.18:
            return True
        if catalog_row_ratio >= 0.12 and row_end_page_ratio >= 0.4 and avg_cols <= 4.2:
            return True
        if chapter_hits > 0 and page_hits > 0 and len(cleaned_headers) <= 4 and (numeric_ratio < 0.35 or len(data_rows) <= 6):
            return True
        if figure_hits > 0 and int(runtime_page_count or 0) <= 120:
            has_year_span = any(re.search(r"20\d{2}\s*[-—~至]\s*20\d{2}", header) for header in cleaned_headers)
            growth_label = any(("增长速度" in header) or ("增速" in header) for header in cleaned_headers)
            if has_year_span and len(data_rows) <= 3 and avg_cols <= 6.2:
                return True
            if growth_label and sentence_like_ratio <= 0.22 and len(data_rows) <= 3 and avg_cols <= 6.2:
                return True
        if catalog_hits > 0 and len(cleaned_headers) <= 5 and len(data_rows) <= 10:
            return True
        if catalog_hits > 0 and avg_cols <= 4.5 and numeric_ratio < 0.55:
            return True
        if chapter_hits > 0 and len(cleaned_headers) <= 2 and numeric_ratio < 0.6 and len(data_rows) <= 8:
            return True
        if equation_hits > 0 and page_hits > 0 and avg_cols <= 3.2 and len(data_rows) <= 8:
            return True
        if equation_hits >= 2 and avg_cols <= 3.2 and len(data_rows) <= 8:
            return True
        if len(cleaned_headers) <= 1 and len(cleaned_headers[0]) >= 28 and avg_cols <= 2.2 and len(data_rows) <= 8 and numeric_ratio < 0.3:
            return True
        if len(cleaned_headers) <= 2 and avg_cols <= 2.2 and long_ratio >= 0.45 and numeric_ratio < 0.25:
            return True
        if numeric_ratio < 0.08 and avg_cols <= 2.2 and len(data_rows) <= 4:
            return True
        if sentence_like_ratio >= 0.62 and avg_cols <= 3.0 and numeric_ratio < 0.2:
            return True
        if sentence_like_ratio >= 0.5 and avg_cols <= 2.2 and numeric_ratio < 0.28:
            return True
        if len(data_rows) <= 6 and avg_cols >= 5.0 and sentence_like_ratio >= 0.25 and numeric_ratio < 0.45:
            return True
        if len(data_rows) <= 5 and avg_cols >= 4.0 and long_ratio >= 0.35 and numeric_ratio < 0.4:
            return True
        return False

    def table_quality_score(self, group: List[Dict[str, Any]], anchors: List[float]) -> float:
        if not group or not anchors:
            return 0.0

        row_count = len(group)
        col_count = len(anchors)
        row_lengths = [len(row.get("cells", [])) for row in group]
        avg_cols = (sum(row_lengths) / float(max(row_count, 1))) if row_lengths else 0.0
        col_coverage = min(1.0, avg_cols / float(max(col_count, 1)))
        row_score = min(1.0, row_count / 6.0)
        col_score = min(1.0, col_count / 6.0)

        align_scores: List[float] = []
        numeric_like = 0
        total_cells = 0
        for idx, row in enumerate(group):
            cells = row.get("cells", [])
            total_cells += len(cells)
            for cell in cells:
                text = str(cell.get("text", "")).strip()
                if re.search(r"\d", text):
                    numeric_like += 1
            if idx > 0:
                align_scores.append(
                    self.row_alignment_score(group[idx - 1].get("cells", []), cells, self.ocr_table_col_tol)
                )
        align_score = (sum(align_scores) / len(align_scores)) if align_scores else 0.0
        numeric_ratio = (numeric_like / float(total_cells)) if total_cells else 0.0
        numeric_score = min(1.0, numeric_ratio * 1.8 + 0.2)

        quality = (
            0.25 * row_score
            + 0.2 * col_score
            + 0.25 * align_score
            + 0.15 * col_coverage
            + 0.15 * numeric_score
        )
        return max(0.0, min(1.0, quality))

    @staticmethod
    def dedupe_ocr_cells(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not cells:
            return []
        ordered = sorted(
            cells,
            key=lambda cell: (
                round(float(cell.get("x_center", 0.0)), 4),
                round(float(cell.get("y_center", 0.0)), 4),
                str(cell.get("text", "")),
            ),
        )
        out: List[Dict[str, Any]] = []
        for cell in ordered:
            x = float(cell.get("x_center", 0.0))
            y = float(cell.get("y_center", 0.0))
            text = str(cell.get("text", "")).strip()
            if not text:
                continue
            duplicated = False
            for prev in out[-12:]:
                if text != str(prev.get("text", "")).strip():
                    continue
                if abs(x - float(prev.get("x_center", 0.0))) <= 0.006 and abs(y - float(prev.get("y_center", 0.0))) <= 0.006:
                    duplicated = True
                    break
            if not duplicated:
                out.append(cell)
        return out

    @staticmethod
    def build_col_anchors(rows: List[Dict[str, Any]], tol: float) -> List[float]:
        xs: List[float] = []
        for row in rows:
            xs.extend(float(cell.get("x_center", 0.0)) for cell in row.get("cells", []))
        xs.sort()
        if not xs:
            return []

        anchors: List[float] = []
        counts: List[int] = []
        for x in xs:
            if not anchors:
                anchors.append(x)
                counts.append(1)
                continue
            if abs(x - anchors[-1]) <= tol:
                count = counts[-1] + 1
                anchors[-1] = ((anchors[-1] * counts[-1]) + x) / count
                counts[-1] = count
            else:
                anchors.append(x)
                counts.append(1)
        return anchors

    @staticmethod
    def nearest_anchor_index(x: float, anchors: List[float]) -> int:
        if not anchors:
            return 0
        best_i = 0
        best_d = abs(x - anchors[0])
        for idx in range(1, len(anchors)):
            dist = abs(x - anchors[idx])
            if dist < best_d:
                best_d = dist
                best_i = idx
        return best_i

    @staticmethod
    def split_table_line(line: str) -> List[str]:
        cleaned = line.strip().strip("|")
        if not cleaned:
            return []
        tokens = [token.strip() for token in re.split(r"\s{2,}|\t|\|", cleaned) if token.strip()]
        if len(tokens) < 2:
            alt = [token.strip() for token in re.split(r"\s+", cleaned) if token.strip()]
            if len(alt) >= 2:
                num_like = sum(1 for token in alt if re.search(r"\d", token))
                if (len(alt) >= 3 and num_like >= 2) or (len(alt) == 2 and num_like >= 1):
                    tokens = alt
        return tokens

    @staticmethod
    def is_table_line(line: str, tokens: List[str]) -> bool:
        if len(tokens) < 2:
            return False
        if len(tokens) >= 3:
            if line.count("|") >= 2 or "\t" in line or re.search(r"\s{2,}", line):
                return True
        if len(tokens) == 2:
            numeric_like = sum(1 for token in tokens if re.search(r"\d", token))
            alpha_like = sum(1 for token in tokens if re.search(r"[A-Za-z\u4e00-\u9fa5]", token))
            if (line.count("|") >= 1 or "\t" in line or re.search(r"\s{2,}", line)) and numeric_like >= 1 and alpha_like >= 1:
                return True
        numeric_like = sum(1 for token in tokens if re.search(r"\d", token))
        return numeric_like >= 2 and len(tokens) >= 4
