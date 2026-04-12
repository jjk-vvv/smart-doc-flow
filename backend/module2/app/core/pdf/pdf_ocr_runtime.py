from __future__ import annotations

import os
import time
from html import escape
from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
PageLines = Dict[int, List[str]]
PageCells = Dict[int, List[Dict[str, Any]]]

GetOcrEngine = Callable[[], Any]
SetRuntimePageCount = Callable[[int], None]
NormalizeText = Callable[[str], str]
NormalizeBox = Callable[[object, int, int], Tuple[float, float, float, float]]
BuildOcrPageIndices = Callable[[int, List[int] | None], List[int]]
LooksLikeTableCueText = Callable[[str], bool]
InferTablesFromOcrCells = Callable[..., TableBlocks]
AugmentWithLineTables = Callable[[TableBlocks, TableBlocks], TableBlocks]
NeedLineTableAugmentation = Callable[[TableBlocks, PageLines], bool]
SelectLineAugmentationPages = Callable[[PageLines, TableBlocks, List[int] | None], PageLines]
InferTablesFromPageLines = Callable[[PageLines, List[str], Dict[str, List[float]], str], TableBlocks]
SelectUncoveredTableLikePages = Callable[[PageLines, TableBlocks, bool], PageLines]
InferFiguresFromPageLines = Callable[..., FigureBlocks]
EnhanceLowQualityPagesWithGeminiVision = Callable[..., Tuple[TableBlocks, FigureBlocks]]
MergeFigureBlocks = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]
PruneFragmentTables = Callable[[TableBlocks], TableBlocks]


class PdfOcrRuntime:
    """Execute the PDF OCR fallback pipeline while keeping parser interfaces stable."""

    def __init__(
        self,
        *,
        ocr_large_doc_dpi: int,
        ocr_large_doc_page_threshold: int,
        ocr_low_priority_dpi: int,
        ocr_high_priority_pages: int,
        ocr_dense_cue_threshold: int,
        ocr_max_attempt_pages_dense_cue: int,
        ocr_max_attempt_pages_mid_cue: int,
        ocr_dynamic_neighbor_pages: int,
        ocr_dynamic_neighbor_auto_enable: bool,
        ocr_dynamic_neighbor_auto_max: int,
        ocr_min_pages_before_budget: int,
        ocr_front_scan_pages: int,
        ocr_low_cue_boost_enable: bool,
        ocr_low_cue_min_pages_cap: int,
        ocr_time_budget_max_sec: float,
        ocr_time_budget_sec: float,
        ocr_time_budget_per_page: float,
        ocr_budget_guard_ratio: float,
        ocr_dynamic_early_stop_enable: bool,
        ocr_dynamic_early_stop_min_pages: int,
        ocr_dynamic_early_stop_min_signal_pages: int,
        ocr_dynamic_early_stop_streak: int,
        ocr_relaxed_trigger_table_count: int,
        ocr_table_relaxed_min_quality: float,
        ocr_table_min_quality: float,
        ocr_uncovered_line_aug_pages: int,
        get_ocr_engine: GetOcrEngine,
        set_runtime_page_count: SetRuntimePageCount,
        normalize_text: NormalizeText,
        normalize_box: NormalizeBox,
        build_ocr_page_indices: BuildOcrPageIndices,
        looks_like_table_cue_text: LooksLikeTableCueText,
        infer_tables_from_ocr_cells: InferTablesFromOcrCells,
        augment_with_line_tables: AugmentWithLineTables,
        need_line_table_augmentation: NeedLineTableAugmentation,
        select_line_augmentation_pages: SelectLineAugmentationPages,
        infer_tables_from_page_lines: InferTablesFromPageLines,
        select_uncovered_table_like_pages: SelectUncoveredTableLikePages,
        infer_figures_from_page_lines: InferFiguresFromPageLines,
        enhance_low_quality_pages_with_gemini_vision: EnhanceLowQualityPagesWithGeminiVision,
        merge_figure_blocks: MergeFigureBlocks,
        prune_fragment_tables: PruneFragmentTables,
    ) -> None:
        self.ocr_large_doc_dpi = int(ocr_large_doc_dpi or 0)
        self.ocr_large_doc_page_threshold = int(ocr_large_doc_page_threshold or 0)
        self.ocr_low_priority_dpi = int(ocr_low_priority_dpi or 0)
        self.ocr_high_priority_pages = int(ocr_high_priority_pages or 0)
        self.ocr_dense_cue_threshold = int(ocr_dense_cue_threshold or 0)
        self.ocr_max_attempt_pages_dense_cue = int(ocr_max_attempt_pages_dense_cue or 0)
        self.ocr_max_attempt_pages_mid_cue = int(ocr_max_attempt_pages_mid_cue or 0)
        self.ocr_dynamic_neighbor_pages = int(ocr_dynamic_neighbor_pages or 0)
        self.ocr_dynamic_neighbor_auto_enable = bool(ocr_dynamic_neighbor_auto_enable)
        self.ocr_dynamic_neighbor_auto_max = int(ocr_dynamic_neighbor_auto_max or 0)
        self.ocr_min_pages_before_budget = int(ocr_min_pages_before_budget or 0)
        self.ocr_front_scan_pages = int(ocr_front_scan_pages or 0)
        self.ocr_low_cue_boost_enable = bool(ocr_low_cue_boost_enable)
        self.ocr_low_cue_min_pages_cap = int(ocr_low_cue_min_pages_cap or 0)
        self.ocr_time_budget_max_sec = float(ocr_time_budget_max_sec or 0.0)
        self.ocr_time_budget_sec = float(ocr_time_budget_sec or 0.0)
        self.ocr_time_budget_per_page = float(ocr_time_budget_per_page or 0.0)
        self.ocr_budget_guard_ratio = float(ocr_budget_guard_ratio or 0.0)
        self.ocr_dynamic_early_stop_enable = bool(ocr_dynamic_early_stop_enable)
        self.ocr_dynamic_early_stop_min_pages = int(ocr_dynamic_early_stop_min_pages or 0)
        self.ocr_dynamic_early_stop_min_signal_pages = int(ocr_dynamic_early_stop_min_signal_pages or 0)
        self.ocr_dynamic_early_stop_streak = int(ocr_dynamic_early_stop_streak or 0)
        self.ocr_relaxed_trigger_table_count = int(ocr_relaxed_trigger_table_count or 0)
        self.ocr_table_relaxed_min_quality = float(ocr_table_relaxed_min_quality or 0.0)
        self.ocr_table_min_quality = float(ocr_table_min_quality or 0.0)
        self.ocr_uncovered_line_aug_pages = int(ocr_uncovered_line_aug_pages or 0)
        self._get_ocr_engine = get_ocr_engine
        self._set_runtime_page_count = set_runtime_page_count
        self._normalize_text = normalize_text
        self._normalize_box = normalize_box
        self._build_ocr_page_indices = build_ocr_page_indices
        self._looks_like_table_cue_text = looks_like_table_cue_text
        self._infer_tables_from_ocr_cells = infer_tables_from_ocr_cells
        self._augment_with_line_tables = augment_with_line_tables
        self._need_line_table_augmentation = need_line_table_augmentation
        self._select_line_augmentation_pages = select_line_augmentation_pages
        self._infer_tables_from_page_lines = infer_tables_from_page_lines
        self._select_uncovered_table_like_pages = select_uncovered_table_like_pages
        self._infer_figures_from_page_lines = infer_figures_from_page_lines
        self._enhance_low_quality_pages_with_gemini_vision = enhance_low_quality_pages_with_gemini_vision
        self._merge_figure_blocks = merge_figure_blocks
        self._prune_fragment_tables = prune_fragment_tables

    def parse_pdf_with_ocr(
        self,
        file_bytes: bytes,
        page_count: int,
        cue_pages: List[int] | None = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks, FigureBlocks]:
        try:
            import fitz  # pymupdf
            import numpy as np
        except Exception as exc:
            raise ValueError(
                "VisualTrack OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
            ) from exc

        base_dpi = max(96, int(os.getenv("MODULE2_OCR_DPI", "120")))
        self._set_runtime_page_count(page_count)
        dpi = min(base_dpi, self.ocr_large_doc_dpi) if page_count >= self.ocr_large_doc_page_threshold else base_dpi
        low_dpi = min(dpi, self.ocr_low_priority_dpi)
        min_conf = float(os.getenv("MODULE2_OCR_MIN_CONF", "0.45"))
        mat_high = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        mat_low = fitz.Matrix(low_dpi / 72.0, low_dpi / 72.0)
        engine = self._get_ocr_engine()

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_lines: PageLines = {}
        page_cells: PageCells = {}

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
            int(page_no)
            for page_no in (cue_pages or [])
            if isinstance(page_no, int)
        }
        dense_cue = cue_count >= self.ocr_dense_cue_threshold
        max_attempt_pages: int | None = None
        if dense_cue:
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_dense_cue)
        elif cue_count >= max(40, self.ocr_dense_cue_threshold // 2):
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_mid_cue)
        dynamic_neighbor_budget = self.ocr_dynamic_neighbor_pages
        if dynamic_neighbor_budget <= 0 and self.ocr_dynamic_neighbor_auto_enable and self.ocr_dynamic_neighbor_auto_max > 0:
            if cue_count <= 0:
                if len(queue) <= 72:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 8)
                elif len(queue) <= 110:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 6)
                else:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 4)
            elif cue_count < max(10, self.ocr_dense_cue_threshold // 12):
                dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 4)
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
        if cue_count <= 0 and self.ocr_front_scan_pages > 0:
            min_pages_before_budget = max(
                min_pages_before_budget,
                min(len(queue), self.ocr_front_scan_pages),
            )
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
                    if dynamic_neighbor_budget > 0 and dynamic_added < dynamic_neighbor_budget:
                        cells_cur = page_cells.get(page_no, [])
                        top_dense = sum(1 for cell in cells_cur if float(cell.get("y_center", 0.0)) <= 0.14) >= 3
                        bottom_dense = sum(1 for cell in cells_cur if float(cell.get("y_center", 0.0)) >= 0.86) >= 3
                        if has_table_cue or has_numeric_table_rows or top_dense or bottom_dense:
                            neighbor_order: List[int] = []
                            if bottom_dense:
                                neighbor_order.append(page_idx + 1)
                            if top_dense:
                                neighbor_order.append(page_idx - 1)
                            if not neighbor_order:
                                neighbor_order = [page_idx + 1, page_idx - 1]
                            for cand in neighbor_order:
                                if dynamic_added >= dynamic_neighbor_budget:
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

        figure_blocks = self._infer_figures_from_page_lines(
            page_lines=page_lines,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="pdf_ocr_caption",
        )

        table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
            file_bytes=file_bytes,
            filetype="pdf",
            page_lines=page_lines,
            table_blocks=table_blocks,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="pdf_gemini_vision",
        )
        if vision_figures:
            figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)
        table_blocks = self._prune_fragment_tables(table_blocks)
        return "\n".join(parts), bbox_map, table_blocks, figure_blocks
