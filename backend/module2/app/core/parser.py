from __future__ import annotations

import io
import os
import re
import time
from html import escape
from typing import Any, Dict, List, Tuple

from pypdf import PdfReader


TableBlocks = List[Dict[str, Any]]


class NativeDocumentParser:
    """Native parser pipeline (PDF/DOCX/XLSX) with built-in libraries only."""

    _ocr_engine = None

    def __init__(self, max_pages: int | None = None) -> None:
        self.max_pages = max_pages or max(1, int(os.getenv("MODULE2_MAX_PARSE_PAGES", "120")))
        self.max_pages_visual = max(
            self.max_pages,
            int(os.getenv("MODULE2_MAX_PARSE_PAGES_VISUAL", "480")),
        )
        self.visual_probe_pages = max(1, int(os.getenv("MODULE2_VISUAL_PROBE_PAGES", "12")))
        self.native_text_threshold = max(120, int(os.getenv("MODULE2_NATIVE_TEXT_THRESHOLD", "200")))
        self.ocr_max_pages = max(1, int(os.getenv("MODULE2_OCR_MAX_PAGES", "4")))
        self.ocr_extra_sample_pages = max(0, int(os.getenv("MODULE2_OCR_EXTRA_SAMPLE_PAGES", "10")))
        self.ocr_time_budget_sec = max(10.0, float(os.getenv("MODULE2_OCR_TIME_BUDGET_SEC", "90")))
        self.ocr_time_budget_per_page = max(0.2, float(os.getenv("MODULE2_OCR_TIME_BUDGET_PER_PAGE", "2.8")))
        self.ocr_time_budget_max_sec = max(
            self.ocr_time_budget_sec,
            float(os.getenv("MODULE2_OCR_TIME_BUDGET_MAX_SEC", "300")),
        )
        self.ocr_budget_guard_ratio = max(
            0.5,
            min(0.98, float(os.getenv("MODULE2_OCR_BUDGET_GUARD_RATIO", "0.90"))),
        )
        self.ocr_min_pages_before_budget = max(3, int(os.getenv("MODULE2_OCR_MIN_PAGES_BEFORE_BUDGET", "22")))
        self.ocr_cue_scan_pages = max(
            self.visual_probe_pages,
            int(os.getenv("MODULE2_OCR_CUE_SCAN_PAGES", str(self.max_pages_visual))),
        )
        self.ocr_cue_max_pages = max(0, int(os.getenv("MODULE2_OCR_CUE_MAX_PAGES", "220")))
        self.ocr_cue_boost_max_pages = max(1, int(os.getenv("MODULE2_OCR_CUE_BOOST_MAX_PAGES", "110")))
        self.ocr_cue_neighbor = max(0, int(os.getenv("MODULE2_OCR_CUE_NEIGHBOR", "1")))
        self.visual_weak_table_min = max(1, int(os.getenv("MODULE2_VISUAL_WEAK_TABLE_MIN", "4")))
        self.visual_weak_table_quality = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_VISUAL_WEAK_TABLE_QUALITY", "0.35"))),
        )
        self.visual_force_ocr_on_weak_native = (
            os.getenv("MODULE2_VISUAL_FORCE_OCR_ON_WEAK_NATIVE", "true").lower() in {"1", "true", "yes"}
        )
        self.ocr_min_coverage_ratio = min(
            1.0,
            max(0.02, float(os.getenv("MODULE2_OCR_MIN_COVERAGE_RATIO", "0.14"))),
        )
        self.ocr_max_scan_pages = max(1, int(os.getenv("MODULE2_OCR_MAX_SCAN_PAGES", "96")))
        self.ocr_min_scan_pages = max(1, int(os.getenv("MODULE2_OCR_MIN_SCAN_PAGES", "28")))
        self.ocr_large_doc_page_threshold = max(50, int(os.getenv("MODULE2_OCR_LARGE_DOC_PAGE_THRESHOLD", "220")))
        self.ocr_large_doc_dpi = max(72, int(os.getenv("MODULE2_OCR_LARGE_DOC_DPI", "96")))
        self.ocr_low_priority_dpi = max(72, int(os.getenv("MODULE2_OCR_LOW_PRIORITY_DPI", "84")))
        self.ocr_high_priority_pages = max(1, int(os.getenv("MODULE2_OCR_HIGH_PRIORITY_PAGES", "14")))
        self.ocr_dense_cue_threshold = max(20, int(os.getenv("MODULE2_OCR_DENSE_CUE_THRESHOLD", "160")))
        self.ocr_max_attempt_pages_dense_cue = max(16, int(os.getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_DENSE_CUE", "72")))
        self.ocr_max_attempt_pages_mid_cue = max(
            self.ocr_max_attempt_pages_dense_cue,
            int(os.getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_MID_CUE", "84")),
        )
        self.ocr_dynamic_neighbor_pages = max(0, int(os.getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_PAGES", "0")))
        self.ocr_dynamic_early_stop_enable = (
            os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_ENABLE", "true").lower() in {"1", "true", "yes"}
        )
        self.ocr_dynamic_early_stop_min_pages = max(
            12,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_PAGES", "34")),
        )
        self.ocr_dynamic_early_stop_streak = max(
            4,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_STREAK", "14")),
        )
        self.ocr_dynamic_early_stop_min_signal_pages = max(
            2,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_SIGNAL_PAGES", "8")),
        )
        self.ocr_low_cue_boost_enable = (
            os.getenv("MODULE2_OCR_LOW_CUE_BOOST_ENABLE", "false").lower() in {"1", "true", "yes"}
        )
        self.ocr_low_cue_min_pages_cap = max(
            24,
            int(os.getenv("MODULE2_OCR_LOW_CUE_MIN_PAGES_CAP", "44")),
        )
        self.enable_fitz_table = os.getenv("MODULE2_ENABLE_FITZ_TABLE", "true").lower() in {"1", "true", "yes"}
        self.ocr_table_min_cols = max(2, int(os.getenv("MODULE2_OCR_TABLE_MIN_COLS", "2")))
        self.ocr_table_min_rows = max(2, int(os.getenv("MODULE2_OCR_TABLE_MIN_ROWS", "2")))
        self.ocr_table_row_tol = max(0.006, float(os.getenv("MODULE2_OCR_TABLE_ROW_TOL", "0.018")))
        self.ocr_table_col_tol = max(0.01, float(os.getenv("MODULE2_OCR_TABLE_COL_TOL", "0.04")))
        self.ocr_table_row_gap = max(0.02, float(os.getenv("MODULE2_OCR_TABLE_ROW_GAP", "0.08")))
        self.ocr_table_relaxed_row_gap_scale = max(
            1.0,
            float(os.getenv("MODULE2_OCR_TABLE_RELAXED_ROW_GAP_SCALE", "1.5")),
        )
        self.ocr_table_relaxed_align_min = max(
            0.1,
            min(0.9, float(os.getenv("MODULE2_OCR_TABLE_RELAXED_ALIGN_MIN", "0.36"))),
        )
        self.ocr_table_relaxed_overlap_min = max(
            0.1,
            min(0.9, float(os.getenv("MODULE2_OCR_TABLE_RELAXED_OVERLAP_MIN", "0.3"))),
        )
        self.ocr_table_relaxed_col_diff_max = max(
            1,
            int(os.getenv("MODULE2_OCR_TABLE_RELAXED_COL_DIFF_MAX", "2")),
        )
        self.ocr_table_min_quality = max(0.1, float(os.getenv("MODULE2_OCR_TABLE_MIN_QUALITY", "0.52")))
        self.ocr_table_relaxed_min_quality = max(
            0.1,
            min(
                self.ocr_table_min_quality,
                float(os.getenv("MODULE2_OCR_TABLE_RELAXED_MIN_QUALITY", "0.42")),
            ),
        )
        self.ocr_relaxed_trigger_table_count = max(
            1,
            int(os.getenv("MODULE2_OCR_RELAXED_TRIGGER_TABLE_COUNT", "6")),
        )
        self.ocr_line_aug_max_extra_cue_pages = max(
            0,
            int(os.getenv("MODULE2_OCR_LINE_AUG_MAX_EXTRA_CUE_PAGES", "24")),
        )
        self.ocr_uncovered_line_aug_pages = max(
            0,
            int(os.getenv("MODULE2_OCR_UNCOVERED_LINE_AUG_PAGES", "8")),
        )
        self.table_max_rows = max(1, int(os.getenv("MODULE2_TABLE_MAX_ROWS", "120")))
        self.table_max_cols = max(1, int(os.getenv("MODULE2_TABLE_MAX_COLS", "20")))
        self.table_cell_cap = max(200, int(os.getenv("MODULE2_TABLE_CELL_CAP", "3000")))
        self.table_merge_enable = os.getenv("MODULE2_TABLE_MERGE_ENABLE", "true").lower() in {"1", "true", "yes"}
        self.table_merge_max_page_gap = max(1, int(os.getenv("MODULE2_TABLE_MERGE_MAX_PAGE_GAP", "1")))
        self.table_merge_header_sim = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_TABLE_MERGE_HEADER_SIM_THRESHOLD", "0.58"))),
        )
        self.table_merge_col_overlap = max(
            0.3,
            min(1.0, float(os.getenv("MODULE2_TABLE_MERGE_COL_OVERLAP_THRESHOLD", "0.55"))),
        )

    def parse_document(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str = "FastTrack",
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        name = (file_name or "unknown").lower()
        if name.endswith(".pdf"):
            return self._parse_pdf(file_name, file_bytes, track)
        if name.endswith(".docx"):
            return self._parse_docx(file_bytes)
        if name.endswith(".xlsx"):
            return self._parse_xlsx(file_bytes)
        return self._parse_plain(file_bytes)

    def _parse_pdf(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError(f"PDF has no pages: {file_name}")

        cue_pages: List[int] = []
        visual_page_count = min(total_pages, self.max_pages_visual)
        if track == "VisualTrack":
            cue_scan_pages = min(visual_page_count, self.ocr_cue_scan_pages)
            cue_pages = self._collect_table_cue_pages(reader, cue_scan_pages)

        if track == "VisualTrack":
            probe_pages = min(total_pages, self.visual_probe_pages)
            probe_chars = 0
            for page_idx in range(probe_pages):
                page = reader.pages[page_idx]
                probe_chars += len(self._normalize_text(page.extract_text() or ""))
            if probe_chars < self.native_text_threshold:
                return self._parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages)

        page_count = min(total_pages, self.max_pages)

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_texts: List[str] = []
        total_chars = 0

        for page_idx in range(page_count):
            page_no = float(page_idx + 1)
            page = reader.pages[page_idx]
            text = self._normalize_text(page.extract_text() or "")
            page_texts.append(text)
            total_chars += len(text)

            chunks = self._split_page_text(text)
            if not chunks:
                ref_id = f"p{page_idx + 1}_c1"
                placeholder = f"[Page {page_idx + 1}] No extractable native text."
                parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                bbox_map[ref_id] = [page_no, 0.0, 0.0, 1.0, 1.0]
                continue

            for chunk_idx, chunk in enumerate(chunks, start=1):
                ref_id = f"p{page_idx + 1}_c{chunk_idx}"
                parts.append(f'<ref id="{ref_id}">{escape(chunk)}</ref>')
                bbox_map[ref_id] = [page_no, 0.0, 0.0, 1.0, 1.0]

        if track == "VisualTrack" and total_chars < self.native_text_threshold:
            return self._parse_pdf_with_ocr(file_bytes, page_count, cue_pages=cue_pages)

        table_blocks: TableBlocks = []
        if self.enable_fitz_table:
            table_blocks = self._extract_pdf_tables_with_fitz(file_bytes, page_count, parts, bbox_map)
        if not table_blocks:
            table_blocks = self._infer_pdf_tables(page_texts, parts, bbox_map, source="pdf_native")
        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)

        if (
            track == "VisualTrack"
            and self.visual_force_ocr_on_weak_native
            and self._is_weak_native_table_result(table_blocks, cue_pages)
        ):
            return self._parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages)

        return "\n".join(parts), bbox_map, table_blocks

    def _collect_table_cue_pages(self, reader: PdfReader, page_count: int) -> List[int]:
        limit = min(max(page_count, 0), len(reader.pages))
        if limit <= 0:
            return []

        hits: List[int] = []
        for page_idx in range(limit):
            try:
                raw = reader.pages[page_idx].extract_text() or ""
            except Exception:
                continue
            text = self._normalize_text(raw)
            if not text:
                continue
            if self._looks_like_table_cue_text(text):
                hits.append(page_idx)

        if not hits:
            return []
        if self.ocr_cue_max_pages <= 0 or len(hits) <= self.ocr_cue_max_pages:
            return hits

        if self.ocr_cue_max_pages == 1:
            return [hits[len(hits) // 2]]

        step = (len(hits) - 1) / float(self.ocr_cue_max_pages - 1)
        sampled = [hits[int(round(i * step))] for i in range(self.ocr_cue_max_pages)]
        seen = set()
        out: List[int] = []
        for idx in sampled:
            if idx in seen:
                continue
            seen.add(idx)
            out.append(idx)
        return out

    @staticmethod
    def _looks_like_table_cue_text(text: str) -> bool:
        t = str(text or "")
        if not t:
            return False
        cue_pattern = re.compile(
            r"\btable\b|\btab\.\b|list of tables|table of contents|\bannex\b|\bappendix\b|"
            r"\u9644\u8868|\u8868\s*[A-Za-z0-9\u4e00-\u9fa5]+",
            re.IGNORECASE,
        )
        return bool(cue_pattern.search(t))

    def _is_weak_native_table_result(self, table_blocks: TableBlocks, cue_pages: List[int]) -> bool:
        cue_count = len(cue_pages or [])
        if not table_blocks:
            return cue_count > 0

        table_count = len(table_blocks)
        sources = {str(t.get("source", "")).strip().lower() for t in table_blocks}
        quality_vals: List[float] = []
        for t in table_blocks:
            try:
                q = float(t.get("quality"))
                quality_vals.append(q)
            except (TypeError, ValueError):
                continue
        avg_quality = (sum(quality_vals) / float(len(quality_vals))) if quality_vals else 0.0

        weak_by_count = table_count < self.visual_weak_table_min
        weak_by_quality = avg_quality <= self.visual_weak_table_quality
        fitz_only = bool(sources) and all(src == "pdf_fitz" for src in sources)

        if cue_count >= 20 and table_count <= max(2, self.visual_weak_table_min):
            return True
        if cue_count >= 8 and weak_by_count and fitz_only:
            return True
        if cue_count >= 8 and weak_by_quality and fitz_only:
            return True
        if cue_count >= 12 and weak_by_count and weak_by_quality:
            return True
        return False

    @staticmethod
    def _header_token_is_generic(text: str) -> bool:
        t = str(text or "").strip().lower()
        if not t:
            return True
        return bool(re.fullmatch(r"col[_\s\-]?\d{1,3}", t))

    def _effective_header_tokens(self, table: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        header_meta = table.get("header_meta", [])
        if isinstance(header_meta, list) and header_meta:
            for item in header_meta:
                name = self._normalize_text(str(item.get("name", "")))
                if not name:
                    continue
                if self._header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        if not tokens:
            for raw in table.get("headers", []):
                name = self._normalize_text(str(raw or ""))
                if not name:
                    continue
                if self._header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        return tokens

    def _header_similarity(self, left: List[str], right: List[str]) -> float:
        if not left or not right:
            return 0.0

        l = [self._normalize_token_for_compare(x) for x in left]
        r = [self._normalize_token_for_compare(x) for x in right]
        l = [x for x in l if x]
        r = [x for x in r if x]
        if not l or not r:
            return 0.0

        lset = set(l)
        rset = set(r)
        inter = len(lset & rset)
        union = len(lset | rset)
        jaccard = (inter / float(union)) if union else 0.0

        short, long = (l, r) if len(l) <= len(r) else (r, l)
        order_hit = 0
        for idx, tok in enumerate(short):
            if idx < len(long) and tok == long[idx]:
                order_hit += 1
        order_score = order_hit / float(max(len(short), 1))

        return (0.65 * jaccard) + (0.35 * order_score)

    def _table_col_overlap(self, left: Dict[str, Any], right: Dict[str, Any]) -> float:
        lc = int(left.get("col_count", 0) or 0)
        rc = int(right.get("col_count", 0) or 0)
        if lc <= 0:
            lc = max((len(r.get("cells", [])) for r in left.get("rows", [])), default=0)
        if rc <= 0:
            rc = max((len(r.get("cells", [])) for r in right.get("rows", [])), default=0)
        if lc <= 0 or rc <= 0:
            return 0.0
        return min(lc, rc) / float(max(lc, rc))

    @staticmethod
    def _table_vertical_span(table: Dict[str, Any]) -> Tuple[float, float]:
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
                    h = float(bbox[4])
                except (TypeError, ValueError):
                    continue
                if h < 0:
                    continue
                y0 = min(y0, y)
                y1 = max(y1, y + h)
                hit = True
        if not hit:
            return 0.0, 1.0
        return max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))

    @staticmethod
    def _table_row_count(table: Dict[str, Any]) -> int:
        try:
            rv = int(table.get("row_count", 0) or 0)
        except (TypeError, ValueError):
            rv = 0
        if rv > 0:
            return rv
        return len(table.get("rows", []))

    def _should_merge_same_page_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)
        if p_page <= 0 or c_page <= 0 or p_page != c_page:
            return False

        h_sim = self._header_similarity(self._effective_header_tokens(prev), self._effective_header_tokens(curr))
        col_overlap = self._table_col_overlap(prev, curr)
        if col_overlap < 0.5:
            return False

        p_top, p_bottom = self._table_vertical_span(prev)
        c_top, c_bottom = self._table_vertical_span(curr)
        if c_bottom <= p_top:
            gap = p_top - c_bottom
        elif c_top >= p_bottom:
            gap = c_top - p_bottom
        else:
            gap = 0.0
        if gap > 0.09:
            return False

        continuation = self._table_has_continuation_marker(prev) or self._table_has_continuation_marker(curr)
        tiny_fragment = self._table_row_count(prev) <= 2 or self._table_row_count(curr) <= 2

        if col_overlap >= 0.86 and gap <= 0.035:
            return True
        if col_overlap >= 0.74 and gap <= 0.06 and (h_sim >= 0.32 or continuation or tiny_fragment):
            return True
        return False

    def _merge_same_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda t: (
                int(t.get("page", 0) or 0),
                self._table_vertical_span(t)[0],
                str(t.get("table_id", "")),
            ),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self._should_merge_same_page_tables(prev, table):
                merged[-1] = self._merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def _table_has_continuation_marker(self, table: Dict[str, Any]) -> bool:
        headers = [str(h or "").strip().lower() for h in table.get("headers", []) if str(h or "").strip()]
        if not headers:
            return False
        text = " ".join(headers)
        return ("continued" in text) or ("cont." in text) or ("\u7eed\u8868" in text)

    def _extract_table_label(self, table: Dict[str, Any]) -> str:
        headers = [str(h or "").strip() for h in table.get("headers", []) if str(h or "").strip()]
        if not headers:
            return ""
        text = " ".join(headers)
        m = re.search(r"\btable\s+([A-Za-z]?[0-9]+(?:[-.][A-Za-z0-9]+)?)\b", text, re.IGNORECASE)
        if not m:
            return ""
        return m.group(1).lower()

    def _should_merge_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)
        if p_page <= 0 or c_page <= 0:
            return False
        if c_page < p_page:
            return False

        left_h = self._effective_header_tokens(prev)
        right_h = self._effective_header_tokens(curr)
        h_sim = self._header_similarity(left_h, right_h)
        col_overlap = self._table_col_overlap(prev, curr)
        page_gap = c_page - p_page
        _, p_bottom = self._table_vertical_span(prev)
        c_top, _ = self._table_vertical_span(curr)

        if page_gap <= self.table_merge_max_page_gap:
            if h_sim >= self.table_merge_header_sim and col_overlap >= self.table_merge_col_overlap:
                return True

            continuation = self._table_has_continuation_marker(prev) or self._table_has_continuation_marker(curr)
            if continuation and h_sim >= (self.table_merge_header_sim * 0.75) and col_overlap >= 0.5:
                return True
            if (
                p_bottom >= 0.78
                and c_top <= 0.26
                and col_overlap >= 0.72
            ):
                prev_label = self._extract_table_label(prev)
                curr_label = self._extract_table_label(curr)
                same_label = bool(prev_label and curr_label and prev_label == curr_label)
                if continuation or same_label:
                    return True
                if h_sim >= max(0.58, self.table_merge_header_sim + 0.08):
                    return True
                if self._table_row_count(curr) <= 3 and h_sim >= 0.68:
                    return True

        relaxed_gap = max(self.table_merge_max_page_gap, (self.table_merge_max_page_gap * 4))
        if page_gap <= relaxed_gap and h_sim >= 0.9 and col_overlap >= 0.8:
            return True

        if page_gap <= max(10, relaxed_gap):
            prev_label = self._extract_table_label(prev)
            curr_label = self._extract_table_label(curr)
            if prev_label and curr_label and prev_label == curr_label and col_overlap >= 0.5:
                return True

        return False

    def _merge_table_pair(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(prev)
        prev_rows = prev.get("rows", []) if isinstance(prev.get("rows", []), list) else []
        curr_rows = curr.get("rows", []) if isinstance(curr.get("rows", []), list) else []

        out_rows: List[Dict[str, Any]] = []
        row_idx = 1
        for row in (prev_rows + curr_rows):
            cells = row.get("cells", []) if isinstance(row.get("cells", []), list) else []
            cells_out = [dict(c) for c in cells if isinstance(c, dict)]
            if not cells_out:
                continue
            out_rows.append({"row_index": row_idx, "cells": cells_out})
            row_idx += 1

        merged["rows"] = out_rows
        merged["row_count"] = len(out_rows)
        merged["col_count"] = max(
            int(prev.get("col_count", 0) or 0),
            int(curr.get("col_count", 0) or 0),
            max((len(r.get("cells", [])) for r in out_rows), default=0),
        )

        left_h = self._effective_header_tokens(prev)
        right_h = self._effective_header_tokens(curr)
        if len(right_h) > len(left_h):
            merged["headers"] = curr.get("headers", merged.get("headers", []))
            merged["header_meta"] = curr.get("header_meta", merged.get("header_meta", []))

        try:
            q_prev = float(prev.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            q_prev = 0.0
        try:
            q_curr = float(curr.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            q_curr = 0.0
        if (q_prev > 0.0) or (q_curr > 0.0):
            merged["quality"] = round((q_prev + q_curr) / 2.0, 4)

        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)
        start = min(x for x in [p_page, c_page] if x > 0) if (p_page > 0 or c_page > 0) else 0
        end = max(p_page, c_page)
        if start > 0 and end >= start:
            merged["page"] = start
            merged["page_span"] = [start, end]

        merged_from = []
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

    def _merge_cross_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda t: (int(t.get("page", 0) or 0), str(t.get("table_id", ""))),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self._should_merge_tables(prev, table):
                merged[-1] = self._merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def _parse_pdf_with_ocr(
        self,
        file_bytes: bytes,
        page_count: int,
        cue_pages: List[int] | None = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        try:
            import fitz  # pymupdf
            import numpy as np
        except Exception as exc:
            raise ValueError(
                "VisualTrack OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
            ) from exc

        base_dpi = max(96, int(os.getenv("MODULE2_OCR_DPI", "120")))
        dpi = min(base_dpi, self.ocr_large_doc_dpi) if page_count >= self.ocr_large_doc_page_threshold else base_dpi
        low_dpi = min(dpi, self.ocr_low_priority_dpi)
        min_conf = float(os.getenv("MODULE2_OCR_MIN_CONF", "0.45"))
        mat_high = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        mat_low = fitz.Matrix(low_dpi / 72.0, low_dpi / 72.0)
        engine = self._get_ocr_engine()

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_lines: Dict[int, List[str]] = {}
        page_cells: Dict[int, List[Dict[str, Any]]] = {}

        page_indices = self._build_ocr_page_indices(
            page_count=min(page_count, len(doc)),
            cue_pages=cue_pages,
        )
        queue: List[int] = list(page_indices)
        queued = set(queue)
        processed_idx = set()
        dynamic_added = 0
        cue_count = len(cue_pages or [])
        cue_set = {
            int(p)
            for p in (cue_pages or [])
            if isinstance(p, int)
        }
        dense_cue = cue_count >= self.ocr_dense_cue_threshold
        max_attempt_pages: int | None = None
        if dense_cue:
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_dense_cue)
        elif cue_count >= max(40, self.ocr_dense_cue_threshold // 2):
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_mid_cue)
        base_min_pages_before_budget = max(self.ocr_min_pages_before_budget, 3)
        if len(queue) >= 60:
            if cue_count <= 0:
                ratio = 0.60 if self.ocr_low_cue_boost_enable else 0.48
            elif cue_count < 20:
                ratio = 0.42
            else:
                ratio = 0.34
            base_min_pages_before_budget = max(base_min_pages_before_budget, int(round(len(queue) * ratio)))
        elif len(queue) >= 40:
            if cue_count <= 0:
                ratio = 0.54 if self.ocr_low_cue_boost_enable else 0.44
            elif cue_count < 15:
                ratio = 0.38
            else:
                ratio = 0.30
            base_min_pages_before_budget = max(base_min_pages_before_budget, int(round(len(queue) * ratio)))
        if cue_count <= 0 and self.ocr_low_cue_boost_enable:
            base_min_pages_before_budget = min(
                base_min_pages_before_budget,
                min(len(queue), self.ocr_low_cue_min_pages_cap),
            )
        if cue_count >= 80:
            base_min_pages_before_budget = max(base_min_pages_before_budget, 30)
        elif cue_count >= 40:
            base_min_pages_before_budget = max(base_min_pages_before_budget, 26)
        min_pages_before_budget = min(len(queue), base_min_pages_before_budget)
        adaptive_budget = min(
            self.ocr_time_budget_max_sec,
            max(self.ocr_time_budget_sec, len(queue) * self.ocr_time_budget_per_page),
        )
        effective_guard = self.ocr_budget_guard_ratio
        if cue_count >= 120:
            effective_guard = max(effective_guard, 0.98)
        elif cue_count >= 40:
            effective_guard = max(effective_guard, 0.94)
        budget_cutoff = adaptive_budget * effective_guard
        if cue_count >= 80:
            min_pages_before_budget = min(len(queue), max(min_pages_before_budget, 30))
        start_t = time.perf_counter()
        try:
            attempted_pages = 0
            table_signal_pages = 0
            no_signal_streak = 0
            qpos = 0
            while qpos < len(queue):
                if max_attempt_pages is not None and attempted_pages >= max_attempt_pages:
                    break
                if attempted_pages >= min_pages_before_budget and time.perf_counter() - start_t > budget_cutoff:
                    break
                page_idx = queue[qpos]
                qpos += 1
                if page_idx in processed_idx:
                    continue
                processed_idx.add(page_idx)
                attempted_pages += 1

                page_no = page_idx + 1
                page = doc.load_page(page_idx)
                use_high_dpi = attempted_pages <= self.ocr_high_priority_pages
                if not dense_cue and page_idx in cue_set:
                    use_high_dpi = True
                pix = page.get_pixmap(matrix=(mat_high if use_high_dpi else mat_low), alpha=False)
                raw = np.frombuffer(pix.samples, dtype=np.uint8)
                if pix.n == 1:
                    image = raw.reshape(pix.height, pix.width)
                else:
                    image = raw.reshape(pix.height, pix.width, pix.n)
                    if pix.n > 3:
                        image = image[:, :, :3]

                ocr_result, _ = engine(image)
                if not ocr_result:
                    ref_id = f"p{page_no}_ocr1"
                    placeholder = f"[Page {page_no}] OCR found no text."
                    parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                    bbox_map[ref_id] = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    continue

                lines: List[str] = []
                item_idx = 1
                for item in ocr_result:
                    if not isinstance(item, (list, tuple)) or len(item) < 3:
                        continue
                    box, text, score = item[0], str(item[1]).strip(), float(item[2] or 0.0)
                    if not text or score < min_conf:
                        continue

                    normalized = self._normalize_text(text)
                    if not normalized:
                        continue

                    ref_id = f"p{page_no}_ocr{item_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
                    x, y, w, h = self._normalize_box(box, pix.width, pix.height)
                    bbox_map[ref_id] = [float(page_no), x, y, w, h]
                    lines.append(normalized)
                    page_cells.setdefault(page_no, []).append(
                        {
                            "ref_id": ref_id,
                            "text": normalized,
                            "bbox": [float(page_no), x, y, w, h],
                            "x_center": x + (w / 2.0),
                            "y_center": y + (h / 2.0),
                        }
                    )
                    item_idx += 1

                has_table_cue = False
                has_numeric_table_rows = False
                if lines:
                    page_lines[page_no] = lines
                    cue_text = " ".join(lines[:48])
                    has_table_cue = self._looks_like_table_cue_text(cue_text)
                    numeric_row_hits = 0
                    for line in lines[:40]:
                        digit_hits = sum(1 for ch in line if ch.isdigit())
                        if digit_hits >= 2:
                            numeric_row_hits += 1
                        if numeric_row_hits >= 3:
                            break
                    has_numeric_table_rows = numeric_row_hits >= 3
                    if self.ocr_dynamic_neighbor_pages > 0 and dynamic_added < self.ocr_dynamic_neighbor_pages:
                        cells_cur = page_cells.get(page_no, [])
                        top_dense = sum(1 for c in cells_cur if float(c.get("y_center", 0.0)) <= 0.14) >= 3
                        bottom_dense = sum(1 for c in cells_cur if float(c.get("y_center", 0.0)) >= 0.86) >= 3
                        if has_table_cue or top_dense or bottom_dense:
                            neighbor_order: List[int] = []
                            if bottom_dense:
                                neighbor_order.append(page_idx + 1)
                            if top_dense:
                                neighbor_order.append(page_idx - 1)
                            if not neighbor_order:
                                neighbor_order = [page_idx + 1, page_idx - 1]
                            for cand in neighbor_order:
                                if dynamic_added >= self.ocr_dynamic_neighbor_pages:
                                    break
                                if 0 <= cand < len(doc) and cand not in queued and cand not in processed_idx:
                                    queue.append(cand)
                                    queued.add(cand)
                                    dynamic_added += 1
                has_signal = has_table_cue or has_numeric_table_rows
                if has_signal:
                    table_signal_pages += 1
                    no_signal_streak = 0
                else:
                    no_signal_streak += 1
                if attempted_pages >= 3:
                    elapsed = time.perf_counter() - start_t
                    avg_page_sec = elapsed / float(max(attempted_pages, 1))
                    if attempted_pages >= min_pages_before_budget and elapsed + avg_page_sec > budget_cutoff:
                        break
                    if (
                        self.ocr_dynamic_early_stop_enable
                        and cue_count >= max(40, self.ocr_dense_cue_threshold // 2)
                        and attempted_pages >= max(min_pages_before_budget, self.ocr_dynamic_early_stop_min_pages)
                        and table_signal_pages >= self.ocr_dynamic_early_stop_min_signal_pages
                        and no_signal_streak >= self.ocr_dynamic_early_stop_streak
                    ):
                        break
        finally:
            doc.close()

        if not parts:
            raise ValueError(
                "VisualTrack OCR completed but no text was extracted. "
                "Try increasing MODULE2_OCR_MAX_PAGES or MODULE2_OCR_TIME_BUDGET_SEC."
            )

        enable_relaxed_second_pass = cue_count <= max(40, self.ocr_dense_cue_threshold // 2)
        table_blocks = self._infer_tables_from_ocr_cells(
            page_cells,
            enable_relaxed_second_pass=enable_relaxed_second_pass,
        )
        if (
            page_cells
            and len(table_blocks) < self.ocr_relaxed_trigger_table_count
            and self.ocr_table_relaxed_min_quality < self.ocr_table_min_quality
        ):
            relaxed_tables = self._infer_tables_from_ocr_cells(
                page_cells,
                min_quality=self.ocr_table_relaxed_min_quality,
                enable_relaxed_second_pass=enable_relaxed_second_pass,
            )
            if table_blocks:
                table_blocks = self._augment_with_line_tables(table_blocks, relaxed_tables)
            else:
                table_blocks = relaxed_tables
        need_line_aug = self._need_line_table_augmentation(table_blocks, page_lines)
        if not table_blocks or need_line_aug:
            aug_lines = self._select_line_augmentation_pages(page_lines, table_blocks, cue_pages=cue_pages)
            line_tables = self._infer_tables_from_page_lines(aug_lines, parts, bbox_map, source="pdf_ocr_line")
            if table_blocks:
                table_blocks = self._augment_with_line_tables(table_blocks, line_tables)
            else:
                table_blocks = line_tables
        if table_blocks and self.ocr_uncovered_line_aug_pages > 0:
            aggressive_uncovered = (cue_count <= 0) and (len(table_blocks) < 40)
            uncovered_lines = self._select_uncovered_table_like_pages(
                page_lines,
                table_blocks,
                aggressive=aggressive_uncovered,
            )
            if uncovered_lines:
                uncovered_tables = self._infer_tables_from_page_lines(
                    uncovered_lines,
                    parts,
                    bbox_map,
                    source="pdf_ocr_line_extra",
                )
                table_blocks = self._augment_with_line_tables(table_blocks, uncovered_tables)
        return "\n".join(parts), bbox_map, table_blocks

    @classmethod
    def _get_ocr_engine(cls):
        if cls._ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR

            cls._ocr_engine = RapidOCR()
        return cls._ocr_engine

    @staticmethod
    def _normalize_box(box: object, width: int, height: int) -> Tuple[float, float, float, float]:
        if not isinstance(box, (list, tuple)) or not box:
            return 0.0, 0.0, 1.0, 1.0

        points: List[Tuple[float, float]] = []
        for p in box:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                try:
                    points.append((float(p[0]), float(p[1])))
                except (TypeError, ValueError):
                    continue

        if not points:
            return 0.0, 0.0, 1.0, 1.0

        x0 = max(0.0, min(pt[0] for pt in points)) / max(width, 1)
        y0 = max(0.0, min(pt[1] for pt in points)) / max(height, 1)
        x1 = max(0.0, max(pt[0] for pt in points)) / max(width, 1)
        y1 = max(0.0, max(pt[1] for pt in points)) / max(height, 1)
        return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)

    def _parse_docx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        ref_idx = 1

        for para in doc.paragraphs:
            text = self._normalize_text(para.text or "")
            if not text:
                continue
            ref_id = f"docx_{ref_idx}"
            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
            ref_idx += 1

        for table_idx, table in enumerate(doc.tables, start=1):
            table_id = f"docx_t{table_idx}"
            rows_payload: List[Dict[str, Any]] = []
            for row_idx, row in enumerate(table.rows[: self.table_max_rows], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell in enumerate(row.cells[: self.table_max_cols], start=1):
                    cell_text = self._normalize_text(cell.text or "")
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if cell_text:
                        cell_ref = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(cell_text)}</ref>')
                        bbox_map[cell_ref] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": cell_text,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                if any(cell.get("text") for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})

            if not rows_payload:
                continue

            headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if not data_rows:
                continue

            table_blocks.append(
                {
                    "table_id": table_id,
                    "source": "docx",
                    "page": 1,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                }
            )

        if not parts:
            raise ValueError("DOCX contains no extractable text.")
        return "\n".join(parts), bbox_map, table_blocks

    def _parse_xlsx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        emitted_cells = 0

        for sheet_idx, ws in enumerate(wb.worksheets, start=1):
            table_id = f"xlsx_t{sheet_idx}"
            rows_payload: List[Dict[str, Any]] = []

            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if row_idx > self.table_max_rows:
                    break
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, val in enumerate(list(row)[: self.table_max_cols], start=1):
                    text = self._normalize_text("" if val is None else str(val))
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if text:
                        cell_ref = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(text)}</ref>')
                        bbox_map[cell_ref] = bbox
                        emitted_cells += 1
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": text,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                    if emitted_cells >= self.table_cell_cap:
                        break

                if any(cell.get("text") for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})

                if emitted_cells >= self.table_cell_cap:
                    break

            if rows_payload:
                headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
                data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
                data_rows = self._decorate_rows_with_meta(data_rows, headers)
                if not data_rows:
                    continue
                table_blocks.append(
                    {
                        "table_id": table_id,
                        "source": "xlsx",
                        "page": 1,
                        "sheet_name": ws.title,
                        "headers": headers,
                        "header_meta": self._build_header_meta(headers),
                        "rows": data_rows,
                        "row_count": len(data_rows),
                        "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                    }
                )

            if emitted_cells >= self.table_cell_cap:
                break

        if not parts:
            raise ValueError("XLSX contains no extractable rows.")
        return "\n".join(parts), bbox_map, table_blocks

    def _parse_plain(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        text = file_bytes.decode("utf-8", errors="ignore")
        text = self._normalize_text(text)
        if not text:
            raise ValueError("Unsupported file type or empty plain text payload.")
        chunks = self._split_page_text(text)
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        for idx, chunk in enumerate(chunks, start=1):
            ref_id = f"text_{idx}"
            parts.append(f'<ref id="{ref_id}">{escape(chunk)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
        return "\n".join(parts), bbox_map, []

    def _infer_pdf_tables(
        self,
        page_texts: List[str],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source: str,
    ) -> TableBlocks:
        page_lines: Dict[int, List[str]] = {}
        for idx, text in enumerate(page_texts, start=1):
            lines = [self._normalize_text(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                page_lines[idx] = lines
        return self._infer_tables_from_page_lines(page_lines, parts, bbox_map, source=source)

    def _extract_pdf_tables_with_fitz(
        self,
        file_bytes: bytes,
        page_count: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
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
            for page_idx in range(min(page_count, len(doc))):
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
                        vals: List[str] = []
                        for cell in list(row)[: self.table_max_cols]:
                            text = self._normalize_text("" if cell is None else str(cell))
                            vals.append(text)
                        if any(vals):
                            rows_cleaned.append(vals)
                    if len(rows_cleaned) < 2:
                        continue

                    headers = [h for h in rows_cleaned[0] if h]
                    data_rows = rows_cleaned[1:]
                    table_id = f"pdf_fitz_t{table_idx}"
                    table_bbox = self._normalize_table_bbox(getattr(table, "bbox", None), page.rect.width, page.rect.height)

                    rows_payload: List[Dict[str, Any]] = []
                    for row_idx, vals in enumerate(data_rows, start=1):
                        cells_payload: List[Dict[str, Any]] = []
                        for col_idx, text in enumerate(vals[: self.table_max_cols], start=1):
                            if not text:
                                continue
                            ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
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
                            rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                        if emitted_cells >= self.table_cell_cap:
                            break

                    if rows_payload:
                        rows_payload = self._decorate_rows_with_meta(rows_payload, headers)
                        table_blocks.append(
                            {
                                "table_id": table_id,
                                "source": "pdf_fitz",
                                "page": page_no,
                                "headers": headers,
                                "header_meta": self._build_header_meta(headers),
                                "rows": rows_payload,
                                "row_count": len(rows_payload),
                                "col_count": max((len(r.get("cells", [])) for r in rows_payload), default=0),
                            }
                        )
                        table_idx += 1

                if emitted_cells >= self.table_cell_cap:
                    break
        finally:
            doc.close()

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    @staticmethod
    def _normalize_table_bbox(raw_bbox: Any, width: float, height: float) -> Tuple[float, float, float, float]:
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

    def _infer_headers_and_data_rows(
        self, rows_payload: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        if not rows_payload:
            return [], []

        def _row_texts(row: Dict[str, Any]) -> List[str]:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            return [self._normalize_text(str(c.get("text", ""))) for c in cells]

        rows_text = [_row_texts(r) for r in rows_payload]
        row1 = rows_text[0]
        col_count = max(len(row1), max((len(r.get("cells", [])) for r in rows_payload), default=0))

        header_start = 0
        if self._is_caption_like_header_row(row1, col_count) and len(rows_payload) >= 2:
            header_start = 1
            row1 = rows_text[header_start]

        headers = row1[:] if row1 else [f"col_{i+1}" for i in range(col_count)]
        data_rows = rows_payload[header_start + 1 :] if len(rows_payload) > (header_start + 1) else []

        if len(rows_payload) >= (header_start + 2):
            row2 = rows_text[header_start + 1]
            if self._is_unit_row(row2):
                merged = self._merge_header_rows(row1, row2, col_count)
                if any(merged):
                    headers = merged
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )

        if not self._looks_like_header_row(headers):
            if len(rows_payload) >= (header_start + 2):
                alt_header = rows_text[header_start + 1]
                if self._looks_like_header_row(alt_header):
                    headers = alt_header[:]
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )
                else:
                    headers = [f"col_{i+1}" for i in range(max(col_count, 1))]
                    data_rows = rows_payload[header_start:]
            else:
                headers = [f"col_{i+1}" for i in range(max(col_count, 1))]
                data_rows = rows_payload[header_start:]

        headers = [h if h else f"col_{i+1}" for i, h in enumerate(headers)]
        return headers, data_rows

    def _is_caption_like_header_row(self, values: List[str], col_count: int) -> bool:
        non_empty = [self._normalize_text(v) for v in values if self._normalize_text(v)]
        if not non_empty:
            return False
        joined = " ".join(non_empty)
        lower = joined.lower()
        if len(non_empty) <= 2:
            if re.search(r"\btable\b\s*[a-z0-9.\-]*", lower):
                return True
            if re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]*", joined):
                return True
            if "续表" in joined:
                return True
        if len(non_empty) == 1 and len(non_empty[0]) >= 20:
            if self._contains_catalog_marker(joined):
                return True
            if re.search(r"\btable\b", lower):
                return True
        if len(non_empty) <= max(2, col_count // 3) and self._contains_catalog_marker(joined):
            return True
        return False

    def _is_unit_row(self, values: List[str]) -> bool:
        if not values:
            return False
        non_empty = [v for v in values if v]
        if not non_empty:
            return False
        unit_like = sum(1 for v in non_empty if self._is_unit_like_token(v))
        return unit_like / float(len(non_empty)) >= 0.6

    @staticmethod
    def _is_unit_like_token_legacy(text: str) -> bool:
        return NativeDocumentParser._is_unit_like_token(text)

    @staticmethod
    def _merge_header_rows(row1: List[str], row2: List[str], col_count: int) -> List[str]:
        merged: List[str] = []
        for i in range(col_count):
            h1 = row1[i] if i < len(row1) else ""
            h2 = row2[i] if i < len(row2) else ""
            if h1 and h2:
                merged.append(f"{h1} ({h2})")
            elif h1:
                merged.append(h1)
            elif h2:
                merged.append(h2)
            else:
                merged.append("")
        return merged

    def _looks_like_header_row(self, headers: List[str]) -> bool:
        vals = [h.strip() for h in headers if h and h.strip()]
        if not vals:
            return False
        numeric_only = sum(1 for v in vals if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", v))
        if numeric_only / float(len(vals)) > 0.5:
            return False
        return True

    def _drop_redundant_header_like_rows(
        self, rows_payload: List[Dict[str, Any]], headers: List[str]
    ) -> List[Dict[str, Any]]:
        if not rows_payload:
            return rows_payload
        header_norm = [self._normalize_token_for_compare(h) for h in headers]
        filtered: List[Dict[str, Any]] = []
        for row in rows_payload:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            row_vals = [self._normalize_token_for_compare(str(c.get("text", ""))) for c in cells]
            row_vals = row_vals[: len(header_norm)]
            if not row_vals:
                continue

            match = 0
            comparable = 0
            has_number = False
            for i, val in enumerate(row_vals):
                if not val:
                    continue
                if re.search(r"\d", val):
                    has_number = True
                hv = header_norm[i] if i < len(header_norm) else ""
                if hv:
                    comparable += 1
                    if val == hv:
                        match += 1
            ratio = (match / float(comparable)) if comparable else 0.0
            if ratio >= 0.7 and not has_number:
                continue
            filtered.append(row)
        return filtered

    @staticmethod
    def _normalize_token_for_compare_legacy(text: str) -> str:
        t = str(text or "").strip().lower()
        t = re.sub(r"[\s\(\)\[\]锛堬級銆愩€?锛殀/\\,.;锛屻€俔", "", t)
        return t

    def _build_header_meta(self, headers: List[str]) -> List[Dict[str, Any]]:
        meta: List[Dict[str, Any]] = []
        for idx, raw in enumerate(headers, start=1):
            name, unit = self._extract_header_name_and_unit(raw)
            meta.append(
                {
                    "col_index": idx,
                    "raw": raw,
                    "name": name,
                    "name_norm": self._normalize_token_for_compare(name),
                    "unit": unit,
                }
            )
        return meta

    def _decorate_rows_with_meta(self, rows_payload: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
        header_meta = self._build_header_meta(headers)
        header_map = {int(h.get("col_index", 0)): h for h in header_meta}
        decorated: List[Dict[str, Any]] = []
        row_idx = 1
        for row in rows_payload:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            out_cells: List[Dict[str, Any]] = []
            for cell in cells:
                col_idx = int(cell.get("col_index", 0) or 0)
                text = self._normalize_text(str(cell.get("text", "")))
                if not text:
                    continue
                hmeta = header_map.get(col_idx, {"name": f"col_{col_idx}", "name_norm": "", "unit": None})
                num_meta = self._extract_number_meta(text, hmeta.get("unit"))
                out = dict(cell)
                out.update(
                    {
                        "text": text,
                        "header": hmeta.get("name"),
                        "header_norm": hmeta.get("name_norm"),
                        "header_unit": hmeta.get("unit"),
                        "value_type": num_meta.get("value_type"),
                        "numeric_value": num_meta.get("numeric_value"),
                        "ratio_value": num_meta.get("ratio_value"),
                        "detected_unit": num_meta.get("detected_unit"),
                        "normalized_text": num_meta.get("normalized_text"),
                    }
                )
                out_cells.append(out)
            if out_cells:
                decorated.append({"row_index": row_idx, "cells": out_cells})
                row_idx += 1
        return decorated

    def _extract_header_name_and_unit_legacy(self, raw_header: str) -> Tuple[str, Optional[str]]:
        text = self._normalize_text(str(raw_header or ""))
        if not text:
            return "", None
        m = re.match(r"^(.*?)[\(\[锛圿(.+?)[\)\]锛塢\s*$", text)
        if m:
            name = self._normalize_text(m.group(1))
            unit = self._normalize_text(m.group(2))
            return name or text, unit or None
        # Common compact style: 娓╁害/鈩?or flow(L/h)
        m2 = re.match(r"^(.*?)[/锛廬\s*([%掳鈩僡-zA-Z0-9路\-]+)$", text)
        if m2 and len(m2.group(2)) <= 16:
            name = self._normalize_text(m2.group(1))
            unit = self._normalize_text(m2.group(2))
            return name or text, unit or None
        return text, None

    def _extract_number_meta_legacy(self, text: str, unit_hint: Optional[str]) -> Dict[str, Any]:
        return self._extract_number_meta(text, unit_hint)

    def _build_ocr_page_indices(self, page_count: int, cue_pages: List[int] | None = None) -> List[int]:
        if page_count <= 0:
            return []

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

        first_span = min(page_count, self.ocr_max_pages)
        first_indices: List[int] = list(range(first_span))
        base_extra_indices: List[int] = []
        remaining = list(range(first_span, page_count))
        if remaining and self.ocr_extra_sample_pages > 0:
            extra = min(len(remaining), self.ocr_extra_sample_pages)
            base_extra_indices = _even_sample(remaining, extra)
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
                cue_indices = sorted(_even_sample(cue_indices, self.ocr_cue_max_pages))

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
            for idx_local in _even_sample(universe, target - len(selected_set)):
                selected_set.add(idx_local)

        mandatory: List[int] = []
        mandatory_seen = set()
        for idx_local in first_indices + cue_indices + base_extra_indices:
            if idx_local in selected_set and idx_local not in mandatory_seen:
                mandatory.append(idx_local)
                mandatory_seen.add(idx_local)

        if len(selected_set) > hard_cap:
            if len(mandatory) > hard_cap:
                mandatory = _even_sample(mandatory, hard_cap)
                mandatory_seen = set(mandatory)
            rest = sorted(i for i in selected_set if i not in mandatory_seen)
            slots = max(0, hard_cap - len(mandatory))
            trimmed = set(mandatory)
            for idx_local in _even_sample(rest, slots):
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
            anchors = _even_sample(remaining_sorted, anchor_n)
            for idx_local in _interleave_edges(anchors):
                _append(idx_local)
            for idx_local in _interleave_edges(remaining_sorted):
                _append(idx_local)

        return ordered

    def _need_line_table_augmentation(
        self,
        table_blocks: TableBlocks,
        page_lines: Dict[int, List[str]],
    ) -> bool:
        if not page_lines:
            return False
        if not table_blocks:
            return True

        if len(table_blocks) < self.visual_weak_table_min:
            return True

        quality_vals: List[float] = []
        for t in table_blocks:
            try:
                q = float(t.get("quality"))
                quality_vals.append(q)
            except (TypeError, ValueError):
                continue
        if not quality_vals:
            return True

        avg_q = sum(quality_vals) / float(max(len(quality_vals), 1))
        low_q = sum(1 for x in quality_vals if x < max(self.ocr_table_min_quality + 0.08, 0.72))
        low_ratio = low_q / float(max(len(quality_vals), 1))
        if avg_q < 0.8 and low_ratio >= 0.34:
            return True
        return False

    def _select_line_augmentation_pages(
        self,
        page_lines: Dict[int, List[str]],
        base_tables: TableBlocks,
        cue_pages: List[int] | None = None,
    ) -> Dict[int, List[str]]:
        if not page_lines:
            return {}
        if not base_tables:
            return page_lines

        focus_pages = set()
        for t in base_tables:
            p = int(t.get("page", 0) or 0)
            if p <= 0:
                continue
            focus_pages.add(p)
            focus_pages.add(p - 1)
            focus_pages.add(p + 1)

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
            for p in cue_candidates:
                focus_pages.add(p)

        cue_text_pages = [
            p
            for p, lines in page_lines.items()
            if self._looks_like_table_cue_text(" ".join(lines[:18]))
        ]
        if cue_text_pages and self.ocr_line_aug_max_extra_cue_pages > 0:
            for p in cue_text_pages[: self.ocr_line_aug_max_extra_cue_pages]:
                focus_pages.add(p)

        valid = sorted(p for p in focus_pages if p in page_lines)
        if not valid:
            return page_lines

        hard_limit = max(18, min(64, self.ocr_max_scan_pages // 2))
        if len(valid) <= hard_limit:
            return {p: page_lines[p] for p in valid}

        step = (len(valid) - 1) / float(max(hard_limit - 1, 1))
        sampled = [valid[int(round(i * step))] for i in range(hard_limit)]
        sampled = sorted(set(sampled))
        return {p: page_lines[p] for p in sampled}

    def _select_uncovered_table_like_pages(
        self,
        page_lines: Dict[int, List[str]],
        base_tables: TableBlocks,
        aggressive: bool = False,
    ) -> Dict[int, List[str]]:
        if not page_lines or not base_tables or self.ocr_uncovered_line_aug_pages <= 0:
            return {}
        covered_pages = {
            int(t.get("page", 0) or 0)
            for t in base_tables
            if int(t.get("page", 0) or 0) > 0
        }
        min_table_line_hits = 2 if aggressive else 3
        min_numeric_line_hits = 1 if aggressive else 2
        min_score = 6 if aggressive else 9
        max_pages = self.ocr_uncovered_line_aug_pages + (4 if aggressive else 0)
        candidates: List[Tuple[int, int]] = []
        for page_no, lines in page_lines.items():
            if page_no in covered_pages:
                continue
            if not lines:
                continue

            score = 0
            if self._looks_like_table_cue_text(" ".join(lines[:24])):
                score += 2

            table_line_hits = 0
            numeric_line_hits = 0
            for line in lines[:160]:
                tokens = self._split_table_line(line)
                if not self._is_table_line(line, tokens):
                    continue
                table_line_hits += 1
                score += 1
                numeric_hits = sum(1 for t in tokens if re.search(r"\d", t))
                if numeric_hits >= 2:
                    numeric_line_hits += 1
                    score += 1
                if len(tokens) >= 5:
                    score += 1
            if table_line_hits >= min_table_line_hits and numeric_line_hits >= min_numeric_line_hits and score >= min_score:
                candidates.append((score, page_no))

        if not candidates:
            return {}
        chosen = [page for _, page in sorted(candidates, key=lambda x: (-x[0], x[1]))[: max_pages]]
        return {p: page_lines[p] for p in sorted(chosen)}

    def _table_signature(self, table: Dict[str, Any]) -> str:
        page_no = int(table.get("page", 0) or 0)
        headers = [self._normalize_token_for_compare(str(h or "")) for h in table.get("headers", [])]
        headers = [h for h in headers if h][:6]
        col_count = int(table.get("col_count", 0) or 0)
        row_count = int(table.get("row_count", 0) or 0)
        first_row_tokens: List[str] = []
        rows = table.get("rows", [])
        if isinstance(rows, list) and rows:
            first_cells = rows[0].get("cells", []) if isinstance(rows[0], dict) else []
            if isinstance(first_cells, list):
                for c in first_cells[:6]:
                    first_row_tokens.append(self._normalize_token_for_compare(str(c.get("text", ""))))
        first_row_tokens = [x for x in first_row_tokens if x]
        return "|".join(
            [
                str(page_no),
                str(col_count),
                str(row_count),
                ",".join(headers),
                ",".join(first_row_tokens),
            ]
        )

    def _augment_with_line_tables(self, base_tables: TableBlocks, line_tables: TableBlocks) -> TableBlocks:
        if not base_tables:
            return line_tables
        if not line_tables:
            return base_tables

        out: TableBlocks = list(base_tables)
        seen = {self._table_signature(t) for t in base_tables}
        for t in line_tables:
            sig = self._table_signature(t)
            if not sig or sig in seen:
                continue
            rows = int(t.get("row_count", 0) or 0)
            cols = int(t.get("col_count", 0) or 0)
            if rows <= 1 or cols <= 1:
                continue
            out.append(t)
            seen.add(sig)

        if out and self.table_merge_enable:
            out = self._merge_same_page_tables(out)
            out = self._merge_cross_page_tables(out)
        return out

    def _infer_tables_from_ocr_cells(
        self,
        page_cells: Dict[int, List[Dict[str, Any]]],
        min_quality: float | None = None,
        enable_relaxed_second_pass: bool = True,
    ) -> TableBlocks:
        table_blocks: TableBlocks = []
        table_idx = 1
        quality_threshold = self.ocr_table_min_quality if min_quality is None else float(min_quality)

        for page_no in sorted(page_cells.keys()):
            raw_cells = [c for c in page_cells.get(page_no, []) if c.get("text")]
            cells = self._dedupe_ocr_cells(raw_cells)
            if len(cells) < self.ocr_table_min_cols * self.ocr_table_min_rows:
                continue

            dynamic_row_tol = max(self.ocr_table_row_tol, self._median_cell_height(cells) * 1.25)
            rows = self._cluster_ocr_rows(cells, dynamic_row_tol)
            candidate_rows = [row for row in rows if len(row.get("cells", [])) >= self.ocr_table_min_cols]
            if len(candidate_rows) < self.ocr_table_min_rows:
                continue

            groups = self._group_table_rows(candidate_rows)
            page_tables, table_idx = self._build_tables_from_row_groups(
                page_no=page_no,
                groups=groups,
                quality_threshold=quality_threshold,
                table_idx=table_idx,
                all_rows=rows,
            )

            # Second pass: only when strict grouping misses this page, relax row continuity rules.
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
                page_tables, table_idx = self._build_tables_from_row_groups(
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

    def _build_tables_from_row_groups(
        self,
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
                elif base_quality < quality_threshold:
                    continue

                if quality < quality_threshold:
                    continue

                rows_payload: List[Dict[str, Any]] = []
                for row_idx, row in enumerate(use_group[: self.table_max_rows], start=1):
                    row_cells = sorted(row.get("cells", []), key=lambda c: c.get("x_center", 0.0))
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

                if len(rows_payload) < self.ocr_table_min_rows:
                    continue

                headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
                data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
                data_rows = self._decorate_rows_with_meta(data_rows, headers)
                if len(data_rows) < self.ocr_table_min_rows:
                    continue
                if self._looks_like_false_table(headers, data_rows):
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
                        "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                        "quality": round(quality, 4),
                    }
                )
                table_idx += 1
        return page_tables, table_idx

    def _split_group_by_row_gaps(self, group: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        if len(group) < (self.ocr_table_min_rows * 2):
            return [group]
        ordered = sorted(group, key=lambda r: float(r.get("y_center", 0.0)))
        gaps: List[float] = []
        col_counts: List[int] = [len(r.get("cells", [])) for r in ordered]
        for i in range(1, len(ordered)):
            gaps.append(float(ordered[i].get("y_center", 0.0)) - float(ordered[i - 1].get("y_center", 0.0)))
        if not gaps:
            return [ordered]
        sorted_gaps = sorted(gaps)
        mid = len(sorted_gaps) // 2
        median_gap = sorted_gaps[mid] if len(sorted_gaps) % 2 else (sorted_gaps[mid - 1] + sorted_gaps[mid]) / 2.0
        split_threshold = max(self.ocr_table_row_gap * 1.8, median_gap * 2.7)

        parts: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = [ordered[0]]
        for i in range(1, len(ordered)):
            gap = gaps[i - 1]
            prev_cols = col_counts[i - 1]
            curr_cols = col_counts[i]
            col_jump = abs(curr_cols - prev_cols)
            should_split = gap > split_threshold
            if not should_split and gap > (self.ocr_table_row_gap * 1.15) and col_jump >= 3:
                should_split = True
            if should_split and len(current) >= self.ocr_table_min_rows:
                parts.append(current)
                current = [ordered[i]]
            else:
                current.append(ordered[i])
        if current:
            parts.append(current)

        valid = [p for p in parts if len(p) >= self.ocr_table_min_rows]
        if not valid:
            return [ordered]
        if len(valid) == 1:
            return [ordered]
        return valid

    def _expand_group_with_sparse_rows(
        self,
        group: List[Dict[str, Any]],
        anchors: List[float],
        all_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not group or not all_rows or len(all_rows) > 220:
            return group
        group_ids = {id(r) for r in group}
        ys = [float(r.get("y_center", 0.0)) for r in group]
        y_min = min(ys)
        y_max = max(ys)
        y_pad = self.ocr_table_row_gap * 1.0

        group_cells: List[Dict[str, Any]] = []
        for r in group:
            group_cells.extend(r.get("cells", []))
        g_x0, g_x1 = self._cells_x_span(group_cells)

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
            align = self._row_anchor_coverage(cells, anchors, self.ocr_table_col_tol * 1.25)
            overlap = self._cells_span_overlap(cells, g_x0, g_x1)
            has_numeric = any(re.search(r"\d", str(c.get("text", ""))) for c in cells)
            if align >= 0.5 or (len(cells) >= 2 and overlap >= 0.52) or (has_numeric and align >= 0.4 and overlap >= 0.35):
                selected.append(row)

        selected = sorted(selected, key=lambda r: float(r.get("y_center", 0.0)))
        return selected

    @staticmethod
    def _cluster_ocr_rows(cells: List[Dict[str, Any]], row_tol: float) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        ordered = sorted(cells, key=lambda c: (c.get("y_center", 0.0), c.get("x_center", 0.0)))
        for cell in ordered:
            y = float(cell.get("y_center", 0.0))
            placed = False
            for row in rows:
                if abs(y - row["y_center"]) <= row_tol:
                    row["cells"].append(cell)
                    n = len(row["cells"])
                    row["y_center"] = ((row["y_center"] * (n - 1)) + y) / n
                    placed = True
                    break
            if not placed:
                rows.append({"y_center": y, "cells": [cell]})

        rows.sort(key=lambda r: r["y_center"])
        for row in rows:
            row["cells"] = sorted(row["cells"], key=lambda c: c.get("x_center", 0.0))
        return rows

    def _group_table_rows(
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
            align = self._row_alignment_score(prev.get("cells", []), row.get("cells", []), self.ocr_table_col_tol)
            overlap = self._x_overlap_ratio(prev.get("cells", []), row.get("cells", []))
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
    def _row_alignment_score(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]], tol: float) -> float:
        if not cells_a or not cells_b:
            return 0.0
        xs_a = sorted(float(c.get("x_center", 0.0)) for c in cells_a)
        xs_b = sorted(float(c.get("x_center", 0.0)) for c in cells_b)
        short, long = (xs_a, xs_b) if len(xs_a) <= len(xs_b) else (xs_b, xs_a)
        if not short:
            return 0.0

        matched = 0
        for x in short:
            if any(abs(x - y) <= tol for y in long):
                matched += 1
        return matched / float(len(short))

    @staticmethod
    def _x_overlap_ratio(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]]) -> float:
        if not cells_a or not cells_b:
            return 0.0

        def span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
            x0 = min(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) for c in cells)
            x1 = max(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) + float(c.get("bbox", [0, 0, 0, 0, 0])[3]) for c in cells)
            return x0, x1

        a0, a1 = span(cells_a)
        b0, b1 = span(cells_b)
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        den = max(a1 - a0, b1 - b0, 1e-6)
        return inter / den

    @staticmethod
    def _cells_x_span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
        if not cells:
            return 0.0, 1.0
        x0 = min(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) for c in cells)
        x1 = max(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) + float(c.get("bbox", [0, 0, 0, 0, 0])[3]) for c in cells)
        if x1 <= x0:
            return 0.0, 1.0
        return x0, x1

    @staticmethod
    def _cells_span_overlap(cells: List[Dict[str, Any]], x0: float, x1: float) -> float:
        if not cells:
            return 0.0
        c0, c1 = NativeDocumentParser._cells_x_span(cells)
        inter = max(0.0, min(c1, x1) - max(c0, x0))
        den = max(c1 - c0, x1 - x0, 1e-6)
        return inter / den

    @staticmethod
    def _row_anchor_coverage(cells: List[Dict[str, Any]], anchors: List[float], tol: float) -> float:
        if not cells or not anchors:
            return 0.0
        matched = 0
        for c in cells:
            x = float(c.get("x_center", 0.0))
            if any(abs(x - a) <= tol for a in anchors):
                matched += 1
        return matched / float(max(len(cells), 1))

    @staticmethod
    def _median_cell_height(cells: List[Dict[str, Any]]) -> float:
        hs = [float(c.get("bbox", [0, 0, 0, 0, 0])[4]) for c in cells if len(c.get("bbox", [])) >= 5]
        hs = [h for h in hs if h > 0]
        if not hs:
            return 0.015
        hs.sort()
        mid = len(hs) // 2
        if len(hs) % 2:
            return hs[mid]
        return (hs[mid - 1] + hs[mid]) / 2.0

    @staticmethod
    def _is_page_number_token(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.fullmatch(r"[\(\[]?\d{1,4}[\)\]]?", t):
            return True
        return bool(re.fullmatch(r"[\(\[]?[ivxlcdm]{1,8}[\)\]]?", t, re.IGNORECASE))

    @staticmethod
    def _contains_section_marker(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.search(r"\u7b2c.{0,4}[\u7ae0\u8282\u7bc7]", t):
            return True
        if "\u6838\u71c3\u6599\u540e\u5904\u7406\u5de5\u5b66" in t:
            return True
        lower = t.lower()
        if re.search(r"\bchapter\b|\bsection\b|\bcontents\b|table of contents|references", lower):
            return True
        return False

    @staticmethod
    def _contains_equation_marker(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.search(r"\(\d+\-\d+\)", t):
            return True
        if ("=" in t and "+" in t) or ("\u2192" in t) or ("->" in t):
            return True
        return False

    @staticmethod
    def _contains_catalog_marker(text: str) -> bool:
        t = str(text or "").strip().lower()
        if not t:
            return False
        return "list of tables" in t or "table of contents" in t or "contents" == t

    @staticmethod
    def _is_sentence_like_text(text: str) -> bool:
        t = str(text or "").strip()
        if len(t) < 24:
            return False
        if re.search(r"[。；！？]|[A-Za-z]{3,}\s+[A-Za-z]{3,}", t):
            return True
        if t.count(",") + t.count("，") + t.count(";") + t.count("；") >= 2:
            return True
        return False

    def _looks_like_false_table(self, headers: List[str], data_rows: List[Dict[str, Any]]) -> bool:
        if not headers or not data_rows:
            return True

        cleaned_headers = [self._normalize_text(str(h or "")) for h in headers if str(h or "").strip()]
        if not cleaned_headers:
            return True

        chapter_hits = sum(1 for h in cleaned_headers if self._contains_section_marker(h))
        catalog_hits = sum(1 for h in cleaned_headers if self._contains_catalog_marker(h))
        page_hits = sum(1 for h in cleaned_headers if self._is_page_number_token(h))
        equation_hits = sum(1 for h in cleaned_headers if self._contains_equation_marker(h))

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
            row_text = " ".join(self._normalize_text(str(c.get("text", ""))) for c in cells if c.get("text"))
            inspected_rows += 1
            if len(cells) <= 2 and self._is_sentence_like_text(row_text):
                sentence_like_rows += 1
        for cell in flat_cells:
            text = self._normalize_text(str(cell.get("text", "")))
            if not text:
                continue
            if cell.get("numeric_value") is not None or re.search(r"\d", text):
                numeric_cells += 1
            if len(text) >= 24:
                long_text_cells += 1

        total = max(len(flat_cells), 1)
        numeric_ratio = numeric_cells / float(total)
        long_ratio = long_text_cells / float(total)
        sentence_like_ratio = (
            sentence_like_rows / float(max(inspected_rows, 1))
            if inspected_rows > 0
            else 0.0
        )
        avg_cols = (
            sum(len(r.get("cells", [])) for r in data_rows) / float(max(len(data_rows), 1))
            if data_rows
            else 0.0
        )

        # Keep large, consistently tabular blocks to avoid over-filtering text-heavy technical tables.
        if len(data_rows) >= 14 and avg_cols >= 3.2 and sentence_like_ratio <= 0.45:
            return False

        if (
            chapter_hits > 0
            and page_hits > 0
            and len(cleaned_headers) <= 4
            and (numeric_ratio < 0.35 or len(data_rows) <= 6)
        ):
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
        if (
            len(cleaned_headers) <= 1
            and len(cleaned_headers[0]) >= 28
            and avg_cols <= 2.2
            and len(data_rows) <= 8
            and numeric_ratio < 0.3
        ):
            return True
        if len(cleaned_headers) <= 2 and avg_cols <= 2.2 and long_ratio >= 0.45 and numeric_ratio < 0.25:
            return True
        if numeric_ratio < 0.08 and avg_cols <= 2.2 and len(data_rows) <= 4:
            return True
        if sentence_like_ratio >= 0.62 and avg_cols <= 3.0 and numeric_ratio < 0.2:
            return True
        if sentence_like_ratio >= 0.5 and avg_cols <= 2.2 and numeric_ratio < 0.28:
            return True
        return False

    def _table_quality_score(self, group: List[Dict[str, Any]], anchors: List[float]) -> float:
        if not group or not anchors:
            return 0.0

        row_count = len(group)
        col_count = len(anchors)
        row_lengths = [len(r.get("cells", [])) for r in group]
        avg_cols = (sum(row_lengths) / float(max(row_count, 1))) if row_lengths else 0.0
        col_coverage = min(1.0, avg_cols / float(max(col_count, 1)))
        row_score = min(1.0, row_count / 6.0)
        col_score = min(1.0, col_count / 6.0)

        align_scores: List[float] = []
        numeric_like = 0
        total_cells = 0
        for i, row in enumerate(group):
            cells = row.get("cells", [])
            total_cells += len(cells)
            for c in cells:
                text = str(c.get("text", "")).strip()
                if re.search(r"\d", text):
                    numeric_like += 1
            if i > 0:
                align_scores.append(
                    self._row_alignment_score(group[i - 1].get("cells", []), cells, self.ocr_table_col_tol)
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
    def _dedupe_ocr_cells(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not cells:
            return []
        ordered = sorted(
            cells,
            key=lambda c: (
                round(float(c.get("x_center", 0.0)), 4),
                round(float(c.get("y_center", 0.0)), 4),
                str(c.get("text", "")),
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
    def _build_col_anchors(rows: List[Dict[str, Any]], tol: float) -> List[float]:
        xs: List[float] = []
        for row in rows:
            xs.extend(float(c.get("x_center", 0.0)) for c in row.get("cells", []))
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
                n = counts[-1] + 1
                anchors[-1] = ((anchors[-1] * counts[-1]) + x) / n
                counts[-1] = n
            else:
                anchors.append(x)
                counts.append(1)
        return anchors

    @staticmethod
    def _nearest_anchor_index(x: float, anchors: List[float]) -> int:
        if not anchors:
            return 0
        best_i = 0
        best_d = abs(x - anchors[0])
        for i in range(1, len(anchors)):
            d = abs(x - anchors[i])
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    def _infer_tables_from_page_lines(
        self,
        page_lines: Dict[int, List[str]],
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
                header_tokens = group[0][: self.table_max_cols]
                data_rows = group[1 : self.table_max_rows + 1]
                if not data_rows:
                    continue

                table_id = f"{source}_t{table_idx}"
                rows_payload: List[Dict[str, Any]] = []
                for row_idx, row_tokens in enumerate(data_rows, start=1):
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
                        rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                    if emitted_cells >= self.table_cell_cap:
                        break

                if rows_payload:
                    rows_payload = self._decorate_rows_with_meta(rows_payload, header_tokens)
                    if self._looks_like_false_table(header_tokens, rows_payload):
                        continue
                    table_blocks.append(
                        {
                            "table_id": table_id,
                            "source": source,
                            "page": page_no,
                            "headers": header_tokens,
                            "header_meta": self._build_header_meta(header_tokens),
                            "rows": rows_payload,
                            "row_count": len(rows_payload),
                            "col_count": max((len(r.get("cells", [])) for r in rows_payload), default=0),
                        }
                    )
                    table_idx += 1

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    @staticmethod
    def _split_table_line(line: str) -> List[str]:
        cleaned = line.strip().strip("|")
        if not cleaned:
            return []
        tokens = [t.strip() for t in re.split(r"\s{2,}|\t|\|", cleaned) if t.strip()]
        if len(tokens) < 3:
            alt = [t.strip() for t in re.split(r"\s+", cleaned) if t.strip()]
            if len(alt) >= 3:
                num_like = sum(1 for t in alt if re.search(r"\d", t))
                if num_like >= 2:
                    tokens = alt
        return tokens

    @staticmethod
    def _is_table_line(line: str, tokens: List[str]) -> bool:
        if len(tokens) < 3:
            return False
        if line.count("|") >= 2:
            return True
        if "\t" in line:
            return True
        if re.search(r"\s{2,}", line):
            return True
        numeric_like = sum(1 for t in tokens if re.search(r"\d", t))
        if numeric_like >= 2 and len(tokens) >= 4:
            return True
        return False

    @staticmethod
    def _is_unit_like_token(text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        value = value.strip("()[]{}<>（）【】")
        if not value:
            return False
        unit_set = {
            "%", "\uff05", "\u2030",
            "\u2103", "\u00b0c", "\u2109", "\u00b0f",
            "k", "pa", "kpa", "mpa", "bar",
            "s", "sec", "min", "h",
            "g", "kg", "mg", "ug", "\u03bcg",
            "l", "ml", "m3", "m3/h", "l/h",
            "mol", "mol/l", "g/l", "mg/l", "kg/m3",
            "wt%", "vol%", "ppm", "ppb", "ph",
        }
        if value in unit_set:
            return True
        if re.fullmatch(r"[a-z%\u00b0\u2103\u2109\u2030\u03bc/\-0-9]{1,16}", value):
            return True
        return False

    @staticmethod
    def _normalize_token_for_compare(text: str) -> str:
        token = str(text or "").strip().lower()
        token = re.sub(r"[\s\(\)\[\]{}<>/\\,.;:：，、\-_]+", "", token)
        return token

    def _extract_header_name_and_unit(self, raw_header: str) -> Tuple[str, str | None]:
        text = self._normalize_text(str(raw_header or ""))
        if not text:
            return "", None
        m = re.match(r"^(.*?)\s*[\(\[（【]\s*([^\)\]）】]{1,24})\s*[\)\]）】]\s*$", text)
        if m:
            name = self._normalize_text(m.group(1))
            unit = self._normalize_text(m.group(2))
            return name or text, unit or None

        m2 = re.match(r"^(.*?)\s*[/／]\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc0-9\-]{1,16})$", text)
        if m2:
            name = self._normalize_text(m2.group(1))
            unit = self._normalize_text(m2.group(2))
            return name or text, unit or None
        return text, None

    def _extract_number_meta(self, text: str, unit_hint: str | None) -> Dict[str, Any]:
        raw = self._normalize_text(str(text or ""))
        result: Dict[str, Any] = {
            "value_type": "text",
            "numeric_value": None,
            "ratio_value": None,
            "detected_unit": unit_hint,
            "normalized_text": raw,
        }
        if not raw:
            return result

        cleaned = re.sub(r"[,\uFF0C\s]", "", raw)
        sci_text = cleaned.replace("×", "x").replace("X", "x").replace("＊", "x").replace("−", "-")
        sci_match = re.search(r"([-+]?\d*\.?\d+)\s*[x*]\s*10(?:\^)?\s*([-+]?\d+)", sci_text)
        if sci_match:
            try:
                base = float(sci_match.group(1))
                exponent = int(sci_match.group(2))
                value = base * (10.0 ** exponent)
            except ValueError:
                return result
        else:
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned)
            if not m:
                return result
            try:
                value = float(m.group(0))
            except ValueError:
                return result

        scale = 1.0
        if "\u4ebf" in raw:
            scale *= 1e8
        elif "\u4e07" in raw:
            scale *= 1e4
        elif "\u5343" in raw:
            scale *= 1e3
        elif "\u767e" in raw:
            scale *= 1e2

        numeric_value = value * scale
        detected_unit = unit_hint
        if "%" in raw or "\uff05" in raw:
            detected_unit = detected_unit or "%"
            ratio = numeric_value / 100.0
        else:
            ratio = None

        unit_match = re.search(
            r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc/\-]+)$",
            raw,
        )
        if unit_match:
            detected_unit = unit_match.group(1)

        result.update(
            {
                "value_type": "number",
                "numeric_value": round(numeric_value, 10),
                "ratio_value": None if ratio is None else round(ratio, 10),
                "detected_unit": detected_unit,
                "normalized_text": str(round(numeric_value, 10)),
            }
        )
        return result

    @staticmethod
    def _split_page_text(text: str, max_len: int = 700) -> List[str]:
        blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
        chunks: List[str] = []
        for block in blocks:
            if len(block) <= max_len:
                chunks.append(block)
                continue
            for i in range(0, len(block), max_len):
                piece = block[i : i + max_len].strip()
                if piece:
                    chunks.append(piece)
        return chunks

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def parse_document_in_subprocess(
    file_bytes: bytes,
    file_name: str = "document.pdf",
    track: str = "FastTrack",
) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
    """ProcessPool entrypoint (must be top-level and picklable)."""

    parser = NativeDocumentParser()
    return parser.parse_document(file_name=file_name, file_bytes=file_bytes, track=track)

