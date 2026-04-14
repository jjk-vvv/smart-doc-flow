from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
PageLines = Dict[int, List[str]]
ParsePdfWithOcr = Callable[[bytes, int, List[int] | None], Tuple[str, Dict[str, List[float]], TableBlocks]]
NormalizeText = Callable[[str], str]
SplitPageText = Callable[[str], List[str]]
AppendRef = Callable[[List[str], Dict[str, List[float]], str, str, List[float]], None]
CollectTableCuePages = Callable[[Any, int], List[int]]
ExtractPdfTablesWithFitz = Callable[[bytes, int, List[str], Dict[str, List[float]]], TableBlocks]
IsWeakNativeTableResult = Callable[[TableBlocks, List[int]], bool]
SelectLineAugmentationPages = Callable[[PageLines, TableBlocks, List[int] | None], PageLines]
InferTablesFromPageLines = Callable[[PageLines, List[str], Dict[str, List[float]], str], TableBlocks]
AugmentWithLineTables = Callable[[TableBlocks, TableBlocks], TableBlocks]
MergeTables = Callable[[TableBlocks], TableBlocks]
InferFiguresFromPageLines = Callable[[PageLines, List[str], Dict[str, List[float]], str, FigureBlocks], FigureBlocks]
FigureBlocksNeedVision = Callable[[FigureBlocks], bool]
EnhanceLowQualityPagesWithGeminiVision = Callable[..., Tuple[TableBlocks, FigureBlocks]]
MergeFigureBlocks = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]
PruneFragmentTables = Callable[[TableBlocks], TableBlocks]


class PdfNativeParseRuntime:
    """Handle native PDF parsing after visual-first fallback decisions are resolved."""

    def __init__(
        self,
        *,
        max_pages: int,
        max_pages_visual: int,
        visual_probe_pages: int,
        native_text_threshold: int,
        ocr_cue_scan_pages: int,
        enable_fitz_table: bool,
        table_merge_enable: bool,
        visual_force_ocr_on_weak_native: bool,
        gemini_vision_enable_figures: bool,
        normalize_text: NormalizeText,
        split_page_text: SplitPageText,
        append_ref: AppendRef,
        collect_table_cue_pages: CollectTableCuePages,
        extract_pdf_tables_with_fitz: ExtractPdfTablesWithFitz,
        is_weak_native_table_result: IsWeakNativeTableResult,
        select_line_augmentation_pages: SelectLineAugmentationPages,
        infer_tables_from_page_lines: InferTablesFromPageLines,
        augment_with_line_tables: AugmentWithLineTables,
        merge_same_page_tables: MergeTables,
        merge_cross_page_tables: MergeTables,
        infer_figures_from_page_lines: InferFiguresFromPageLines,
        figure_blocks_need_vision: FigureBlocksNeedVision,
        enhance_low_quality_pages_with_gemini_vision: EnhanceLowQualityPagesWithGeminiVision,
        merge_figure_blocks: MergeFigureBlocks,
        prune_fragment_tables: PruneFragmentTables,
    ) -> None:
        self.max_pages = max(1, int(max_pages or 1))
        self.max_pages_visual = max(1, int(max_pages_visual or 1))
        self.visual_probe_pages = max(1, int(visual_probe_pages or 1))
        self.native_text_threshold = max(0, int(native_text_threshold or 0))
        self.ocr_cue_scan_pages = max(1, int(ocr_cue_scan_pages or 1))
        self.enable_fitz_table = bool(enable_fitz_table)
        self.table_merge_enable = bool(table_merge_enable)
        self.visual_force_ocr_on_weak_native = bool(visual_force_ocr_on_weak_native)
        self.gemini_vision_enable_figures = bool(gemini_vision_enable_figures)
        self._normalize_text = normalize_text
        self._split_page_text = split_page_text
        self._append_ref = append_ref
        self._collect_table_cue_pages = collect_table_cue_pages
        self._extract_pdf_tables_with_fitz = extract_pdf_tables_with_fitz
        self._is_weak_native_table_result = is_weak_native_table_result
        self._select_line_augmentation_pages = select_line_augmentation_pages
        self._infer_tables_from_page_lines = infer_tables_from_page_lines
        self._augment_with_line_tables = augment_with_line_tables
        self._merge_same_page_tables = merge_same_page_tables
        self._merge_cross_page_tables = merge_cross_page_tables
        self._infer_figures_from_page_lines = infer_figures_from_page_lines
        self._figure_blocks_need_vision = figure_blocks_need_vision
        self._enhance_low_quality_pages_with_gemini_vision = enhance_low_quality_pages_with_gemini_vision
        self._merge_figure_blocks = merge_figure_blocks
        self._prune_fragment_tables = prune_fragment_tables

    def parse_pdf_native(
        self,
        *,
        reader: Any,
        file_bytes: bytes,
        track: str,
        total_pages: int,
        visual_backend_ready: bool,
        last_figure_blocks: FigureBlocks,
        parse_pdf_with_ocr: ParsePdfWithOcr,
    ) -> Dict[str, Any]:
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
            if probe_chars < self.native_text_threshold and visual_backend_ready:
                return {
                    "early_result": parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages),
                }

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
                self._append_ref(
                    parts,
                    bbox_map,
                    f"p{page_idx + 1}_c1",
                    f"[Page {page_idx + 1}] No extractable native text.",
                    [page_no, 0.0, 0.0, 1.0, 1.0],
                )
                continue

            for chunk_idx, chunk in enumerate(chunks, start=1):
                self._append_ref(
                    parts,
                    bbox_map,
                    f"p{page_idx + 1}_c{chunk_idx}",
                    chunk,
                    [page_no, 0.0, 0.0, 1.0, 1.0],
                )

        if track == "VisualTrack" and total_chars < self.native_text_threshold and visual_backend_ready:
            return {
                "early_result": parse_pdf_with_ocr(file_bytes, page_count, cue_pages=cue_pages),
            }

        native_page_lines: PageLines = {}
        for idx, text in enumerate(page_texts, start=1):
            lines = [self._normalize_text(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                native_page_lines[idx] = lines

        fitz_tables: TableBlocks = []
        if self.enable_fitz_table:
            fitz_tables = self._extract_pdf_tables_with_fitz(
                file_bytes,
                page_count,
                parts,
                bbox_map,
            )
        if fitz_tables:
            weak_fitz = self._is_weak_native_table_result(fitz_tables, cue_pages)
            if weak_fitz:
                line_page_lines = self._select_line_augmentation_pages(
                    native_page_lines,
                    fitz_tables,
                    cue_pages=cue_pages,
                )
                line_tables = self._infer_tables_from_page_lines(
                    line_page_lines,
                    parts,
                    bbox_map,
                    source="pdf_native",
                )
            else:
                line_tables = []
        else:
            line_tables = self._infer_tables_from_page_lines(
                native_page_lines,
                parts,
                bbox_map,
                source="pdf_native",
            )

        if fitz_tables and line_tables:
            table_blocks = self._augment_with_line_tables(fitz_tables, line_tables)
        elif fitz_tables:
            table_blocks = fitz_tables
        else:
            table_blocks = line_tables
        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)

        weak_native_tables = self._is_weak_native_table_result(table_blocks, cue_pages)
        if track == "VisualTrack" and self.visual_force_ocr_on_weak_native and weak_native_tables and visual_backend_ready:
            return {
                "early_result": parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages),
            }

        figure_blocks = self._infer_figures_from_page_lines(
            native_page_lines,
            parts,
            bbox_map,
            "pdf_caption",
            last_figure_blocks,
        )

        shallow_native_figures = self._figure_blocks_need_vision(figure_blocks)
        native_vision_reasons: List[str] = []
        if not visual_backend_ready:
            native_vision_reasons.append("visual_backend_unavailable")
        if weak_native_tables:
            native_vision_reasons.append("weak_native_tables")
        if shallow_native_figures:
            native_vision_reasons.append("shallow_native_figures")
        if self.gemini_vision_enable_figures and page_count >= 20:
            native_vision_reasons.append("large_doc_figure_enrichment")
        should_run_native_vision = track == "VisualTrack" and bool(native_vision_reasons)
        if should_run_native_vision:
            vision_page_lines = dict(native_page_lines)
            for idx in range(1, page_count + 1):
                if idx not in vision_page_lines:
                    vision_page_lines[idx] = [f"[Page {idx}] vision probe"]
            table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
                file_bytes=file_bytes,
                filetype="pdf",
                page_lines=vision_page_lines,
                table_blocks=table_blocks,
                parts=parts,
                bbox_map=bbox_map,
                source_prefix="pdf_gemini_vision_native",
            )
            if vision_figures:
                figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)

        table_blocks = self._prune_fragment_tables(table_blocks)
        return {
            "markdown": "\n".join(parts),
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "figure_blocks": figure_blocks,
            "stats": {
                "image_pages": int(total_pages or 0),
                "image_ref_count": len(bbox_map),
                "image_table_count": len(table_blocks),
                "image_figure_count": len(figure_blocks),
                "native_vision_requested": should_run_native_vision,
                "native_vision_reasons": native_vision_reasons,
                "native_figure_blocks_shallow": shallow_native_figures,
                "native_visual_backend_ready": bool(visual_backend_ready),
            },
        }
