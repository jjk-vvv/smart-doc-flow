from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
PageLines = Dict[int, List[str]]
PageCells = Dict[int, List[Dict[str, Any]]]
Parts = List[str]
BboxMap = Dict[str, List[float]]

SetRuntimePageCount = Callable[[int], None]
AppendRef = Callable[[Parts, BboxMap, str, str, List[float]], None]
NormalizeText = Callable[[str], str]
NormalizeBox = Callable[[object, int, int], Tuple[float, float, float, float]]
ResolveApiKey = Callable[[], str]
CollectPageOcr = Callable[..., Tuple[Parts, BboxMap, PageLines, PageCells]]
BuildParseResult = Callable[..., Tuple[TableBlocks, FigureBlocks]]
VisualBackendAvailable = Callable[[], Tuple[bool, str]]
GetOcrEngine = Callable[[], Any]
InferTablesFromOcrCells = Callable[[PageCells], TableBlocks]
InferTablesFromPageLines = Callable[[PageLines, Parts, BboxMap, str], TableBlocks]
InferFiguresFromPageLines = Callable[[PageLines, Parts, BboxMap, str, FigureBlocks], FigureBlocks]
EnhanceLowQualityPagesWithGeminiVision = Callable[..., Tuple[TableBlocks, FigureBlocks]]
MergeFigureBlocks = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]
PruneFragmentTables = Callable[[TableBlocks], TableBlocks]
SelectLowQualityPages = Callable[[PageLines, TableBlocks], List[int]]
VisionFocusFromPageLines = Callable[[List[str]], str]
RenderPagePngForVision = Callable[[Any], bytes | None]
ExtractPayload = Callable[[bytes, str], Dict[str, Any] | None]
ExtractVisionInsights = Callable[[Dict[str, Any], int, BboxMap], List[Tuple[str, str]]]
BuildTablesFromVisionPayload = Callable[..., Tuple[TableBlocks, int]]
BuildFiguresFromVisionPayload = Callable[..., Tuple[FigureBlocks, int]]
AugmentWithLineTables = Callable[[TableBlocks, TableBlocks], TableBlocks]
NextTableIndex = Callable[[TableBlocks, str], int]
NextFigureIndex = Callable[[FigureBlocks, str], int]


class ImageOcrRuntime:
    """Collect per-page OCR refs, lines, and cells for image-like documents."""

    def __init__(
        self,
        *,
        max_pages_visual: int,
        set_runtime_page_count: SetRuntimePageCount,
        append_ref: AppendRef,
        normalize_text: NormalizeText,
        normalize_box: NormalizeBox,
    ) -> None:
        self.max_pages_visual = max(1, int(max_pages_visual or 1))
        self._set_runtime_page_count = set_runtime_page_count
        self._append_ref = append_ref
        self._normalize_text = normalize_text
        self._normalize_box = normalize_box

    def collect_page_ocr(
        self,
        *,
        doc: Any,
        np_module: Any,
        mat: Any,
        engine: Any,
        min_conf: float,
        visual_backend_ready: bool,
    ) -> Tuple[Parts, BboxMap, PageLines, PageCells]:
        parts: Parts = []
        bbox_map: BboxMap = {}
        page_lines: PageLines = {}
        page_cells: PageCells = {}

        try:
            page_count = min(len(doc), self.max_pages_visual)
            self._set_runtime_page_count(page_count)
            for page_idx in range(page_count):
                page_no = page_idx + 1
                page = doc.load_page(page_idx)
                if not visual_backend_ready:
                    placeholder = f"[Image page {page_no}] OCR backend unavailable, trying Gemini Vision."
                    self._append_ref(
                        parts,
                        bbox_map,
                        f"img_p{page_no}_vision_probe",
                        placeholder,
                        [float(page_no), 0.0, 0.0, 1.0, 1.0],
                    )
                    page_lines[page_no] = [placeholder]
                    continue

                pix = page.get_pixmap(matrix=mat, alpha=False)
                raw = np_module.frombuffer(pix.samples, dtype=np_module.uint8)
                if pix.n == 1:
                    image = raw.reshape(pix.height, pix.width)
                else:
                    image = raw.reshape(pix.height, pix.width, pix.n)
                    if pix.n > 3:
                        image = image[:, :, :3]

                ocr_result, _ = engine(image)
                if not ocr_result:
                    placeholder = f"[Image page {page_no}] OCR found no text."
                    self._append_ref(
                        parts,
                        bbox_map,
                        f"img_p{page_no}_ocr1",
                        placeholder,
                        [float(page_no), 0.0, 0.0, 1.0, 1.0],
                    )
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

                    ref_id = f"img_p{page_no}_ocr{item_idx}"
                    x, y, w, h = self._normalize_box(box, pix.width, pix.height)
                    bbox = [float(page_no), x, y, w, h]
                    self._append_ref(parts, bbox_map, ref_id, normalized, bbox)
                    lines.append(normalized)
                    page_cells.setdefault(page_no, []).append(
                        {
                            "ref_id": ref_id,
                            "text": normalized,
                            "bbox": list(bbox),
                            "x_center": x + (w / 2.0),
                            "y_center": y + (h / 2.0),
                        }
                    )
                    item_idx += 1
                if lines:
                    page_lines[page_no] = lines
        finally:
            doc.close()

        return parts, bbox_map, page_lines, page_cells


class ImageVisionRuntime:
    """Apply Gemini vision enhancement to low-quality image OCR pages."""

    def __init__(
        self,
        *,
        enabled: bool,
        gemini_vision_max_pages: int,
        gemini_vision_consecutive_fail_stop: int,
        resolve_api_key: ResolveApiKey,
        select_low_quality_pages_for_vision: SelectLowQualityPages,
        vision_focus_from_page_lines: VisionFocusFromPageLines,
        render_page_png_for_vision: RenderPagePngForVision,
        extract_payload: ExtractPayload,
        extract_vision_insights: ExtractVisionInsights,
        append_ref: AppendRef,
        build_tables_from_vision_payload: BuildTablesFromVisionPayload,
        build_figures_from_vision_payload: BuildFiguresFromVisionPayload,
        merge_figure_blocks: MergeFigureBlocks,
        augment_with_line_tables: AugmentWithLineTables,
        next_table_index: NextTableIndex,
        next_figure_index: NextFigureIndex,
    ) -> None:
        self.enabled = bool(enabled)
        self.gemini_vision_max_pages = max(0, int(gemini_vision_max_pages or 0))
        self.gemini_vision_consecutive_fail_stop = max(1, int(gemini_vision_consecutive_fail_stop or 1))
        self._resolve_api_key = resolve_api_key
        self._select_low_quality_pages_for_vision = select_low_quality_pages_for_vision
        self._vision_focus_from_page_lines = vision_focus_from_page_lines
        self._render_page_png_for_vision = render_page_png_for_vision
        self._extract_payload = extract_payload
        self._extract_vision_insights = extract_vision_insights
        self._append_ref = append_ref
        self._build_tables_from_vision_payload = build_tables_from_vision_payload
        self._build_figures_from_vision_payload = build_figures_from_vision_payload
        self._merge_figure_blocks = merge_figure_blocks
        self._augment_with_line_tables = augment_with_line_tables
        self._next_table_index = next_table_index
        self._next_figure_index = next_figure_index

    def enhance_low_quality_pages_with_gemini_vision(
        self,
        *,
        file_bytes: bytes,
        filetype: str,
        page_lines: PageLines,
        table_blocks: TableBlocks,
        last_figure_blocks: FigureBlocks,
        parts: Parts,
        bbox_map: BboxMap,
        source_prefix: str,
    ) -> Tuple[TableBlocks, FigureBlocks]:
        if not self.enabled or self.gemini_vision_max_pages <= 0:
            return table_blocks, []

        api_key = self._resolve_api_key()
        if not api_key or not page_lines:
            return table_blocks, []

        candidate_pages = self._select_low_quality_pages_for_vision(page_lines, table_blocks)
        if not candidate_pages:
            return table_blocks, []

        try:
            import fitz  # pymupdf
        except Exception:
            return table_blocks, []

        try:
            doc = fitz.open(stream=file_bytes, filetype=filetype)
        except Exception:
            return table_blocks, []

        try:
            table_idx = self._next_table_index(table_blocks, f"{source_prefix}_t")
            figure_idx = self._next_figure_index(last_figure_blocks, f"{source_prefix}_f")
            vision_tables: TableBlocks = []
            vision_figures: FigureBlocks = []
            consecutive_empty_payload = 0

            for page_no in candidate_pages:
                page_idx = page_no - 1
                if page_idx < 0 or page_idx >= len(doc):
                    continue
                try:
                    page = doc.load_page(page_idx)
                except Exception:
                    continue

                image_png = self._render_page_png_for_vision(page)
                if not image_png:
                    continue

                focus = self._vision_focus_from_page_lines(page_lines.get(page_no, []))
                payload = self._extract_payload(image_png, focus)
                if not payload:
                    consecutive_empty_payload += 1
                    if consecutive_empty_payload >= self.gemini_vision_consecutive_fail_stop:
                        break
                    continue
                consecutive_empty_payload = 0

                insight_refs = self._extract_vision_insights(payload, page_no, bbox_map)
                for ref_id, text in insight_refs:
                    self._append_ref(parts, bbox_map, ref_id, text, [float(page_no), 0.0, 0.0, 1.0, 1.0])

                built_tables, table_idx = self._build_tables_from_vision_payload(
                    payload=payload,
                    page_no=page_no,
                    table_idx=table_idx,
                    parts=parts,
                    bbox_map=bbox_map,
                    source_prefix=source_prefix,
                )
                if built_tables:
                    vision_tables.extend(built_tables)

                built_figures, figure_idx = self._build_figures_from_vision_payload(
                    payload=payload,
                    page_no=page_no,
                    figure_idx=figure_idx,
                    parts=parts,
                    bbox_map=bbox_map,
                    source_prefix=source_prefix,
                )
                if built_figures:
                    vision_figures.extend(built_figures)
        finally:
            doc.close()

        if not vision_tables:
            return table_blocks, self._merge_figure_blocks([], vision_figures)
        if table_blocks:
            return self._augment_with_line_tables(table_blocks, vision_tables), self._merge_figure_blocks([], vision_figures)
        return vision_tables, self._merge_figure_blocks([], vision_figures)


class ImageParseRuntime:
    """Coordinate image OCR post-processing without changing parser-facing behavior."""

    def __init__(
        self,
        *,
        infer_tables_from_ocr_cells: InferTablesFromOcrCells,
        infer_tables_from_page_lines: InferTablesFromPageLines,
        infer_figures_from_page_lines: InferFiguresFromPageLines,
        enhance_low_quality_pages_with_gemini_vision: EnhanceLowQualityPagesWithGeminiVision,
        merge_figure_blocks: MergeFigureBlocks,
        prune_fragment_tables: PruneFragmentTables,
    ) -> None:
        self._infer_tables_from_ocr_cells = infer_tables_from_ocr_cells
        self._infer_tables_from_page_lines = infer_tables_from_page_lines
        self._infer_figures_from_page_lines = infer_figures_from_page_lines
        self._enhance_low_quality_pages_with_gemini_vision = enhance_low_quality_pages_with_gemini_vision
        self._merge_figure_blocks = merge_figure_blocks
        self._prune_fragment_tables = prune_fragment_tables

    def build_parse_result(
        self,
        *,
        visual_backend_ready: bool,
        resolved_gemini_enhance: bool,
        file_bytes: bytes,
        filetype: str,
        page_lines: PageLines,
        page_cells: PageCells,
        last_figure_blocks: FigureBlocks,
        parts: Parts,
        bbox_map: BboxMap,
    ) -> Tuple[TableBlocks, FigureBlocks]:
        table_blocks: TableBlocks = []
        if visual_backend_ready:
            table_blocks = self._infer_tables_from_ocr_cells(page_cells)
        if visual_backend_ready and not table_blocks and page_lines:
            table_blocks = self._infer_tables_from_page_lines(
                page_lines,
                parts,
                bbox_map,
                "image_ocr_line",
            )

        figure_blocks = self._infer_figures_from_page_lines(
            page_lines,
            parts,
            bbox_map,
            "image_caption",
            last_figure_blocks,
        )

        if resolved_gemini_enhance:
            table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
                file_bytes=file_bytes,
                filetype=filetype,
                page_lines=page_lines,
                table_blocks=table_blocks,
                last_figure_blocks=last_figure_blocks,
                parts=parts,
                bbox_map=bbox_map,
                source_prefix="image_gemini_vision",
            )
        else:
            vision_figures = []

        if vision_figures:
            figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)

        return self._prune_fragment_tables(table_blocks), figure_blocks


class ImageDocumentRuntime:
    """Coordinate top-level image parsing without changing OCR and vision internals."""

    def __init__(
        self,
        *,
        enable_gemini_vision_enhance: bool,
        visual_backend_available: VisualBackendAvailable,
        resolve_api_key: ResolveApiKey,
        get_ocr_engine: GetOcrEngine,
        collect_page_ocr: CollectPageOcr,
        build_parse_result: BuildParseResult,
    ) -> None:
        self.enable_gemini_vision_enhance = bool(enable_gemini_vision_enhance)
        self._visual_backend_available = visual_backend_available
        self._resolve_api_key = resolve_api_key
        self._get_ocr_engine = get_ocr_engine
        self._collect_page_ocr = collect_page_ocr
        self._build_parse_result = build_parse_result

    def parse_image(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        last_figure_blocks: FigureBlocks,
        enable_gemini_enhance: Optional[bool] = None,
    ) -> Dict[str, Any]:
        visual_backend_ready, visual_backend_missing = self._visual_backend_available()
        resolved_gemini_enhance = (
            self.enable_gemini_vision_enhance if enable_gemini_enhance is None else bool(enable_gemini_enhance)
        )
        vision_api_ready = bool(self._resolve_api_key()) and resolved_gemini_enhance
        if not visual_backend_ready and not vision_api_ready:
            raise ValueError(
                "Image OCR backend is unavailable. "
                f"Please install: {visual_backend_missing}"
            )

        try:
            import fitz  # pymupdf
        except Exception as exc:
            raise ValueError(
                "Image OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
            ) from exc

        np_module = None
        if visual_backend_ready:
            try:
                import numpy as np_module  # type: ignore
            except Exception as exc:
                raise ValueError(
                    "Image OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
                ) from exc

        ext = os.path.splitext((file_name or "").lower())[1].lstrip(".")
        filetype_candidates = [candidate for candidate in [ext, "png", "jpeg"] if candidate]
        doc = None
        open_error: Exception | None = None
        for filetype in filetype_candidates:
            try:
                doc = fitz.open(stream=file_bytes, filetype=filetype)
                break
            except Exception as exc:  # pragma: no cover - backend-specific decode fallback
                open_error = exc
                continue
        if doc is None:
            raise ValueError(f"Unsupported or corrupted image payload: {file_name}") from open_error

        min_conf = float(os.getenv("MODULE2_OCR_MIN_CONF", "0.45"))
        dpi = max(96, int(os.getenv("MODULE2_IMAGE_OCR_DPI", "180")))
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        engine = self._get_ocr_engine() if visual_backend_ready else None

        parts, bbox_map, page_lines, page_cells = self._collect_page_ocr(
            doc=doc,
            np_module=np_module,
            mat=mat,
            engine=engine,
            min_conf=min_conf,
            visual_backend_ready=visual_backend_ready,
        )
        if visual_backend_ready and not parts:
            raise ValueError("Image OCR completed but no text was extracted.")

        table_blocks, figure_blocks = self._build_parse_result(
            visual_backend_ready=visual_backend_ready,
            resolved_gemini_enhance=resolved_gemini_enhance,
            file_bytes=file_bytes,
            filetype=ext or "png",
            page_lines=page_lines,
            page_cells=page_cells,
            last_figure_blocks=last_figure_blocks,
            parts=parts,
            bbox_map=bbox_map,
        )
        return {
            "markdown": "\n".join(parts),
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "figure_blocks": figure_blocks,
        }
