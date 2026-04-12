from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from ..pdf.pdf_native_parse_runtime import PdfNativeParseRuntime
from ..pdf.pdf_ocr_runtime import PdfOcrRuntime
from ..schema.reference_runtime import ReferenceRuntime
from ..visual.visual_payload_builder import VisualBboxRuntime


RuntimeCallback = Callable[..., Any]
TableBlocks = List[Dict[str, Any]]
ParseResult = Tuple[str, Dict[str, List[float]], TableBlocks]
PdfReaderFactory = Callable[[bytes], Any]
SetRuntimePageCountFn = Callable[[int], None]
ParsePdfWithOcrFn = Callable[..., ParseResult]
BuildPdfRuntimeStateFn = Callable[..., Dict[str, Any]]
BuildVisualParseStateFn = Callable[[Dict[str, Any]], Dict[str, Any]]
ApplyStateUpdateFn = Callable[[Dict[str, Any]], Optional[ParseResult]]
SetLastMineruRunMetaFn = Callable[[Any], None]
SetLastFigureBlocksFn = Callable[[Any], None]
GetCurrentStatsFn = Callable[[], Dict[str, Any]]


class ParserPdfEntryRuntime:
    """Coordinate parser-owned PDF entry adapters without embedding them in parser.py."""

    def prepare_pdf_reader(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        pdf_reader_factory: PdfReaderFactory,
        set_runtime_page_count: SetRuntimePageCountFn,
    ) -> Tuple[Any, int]:
        reader = pdf_reader_factory(file_bytes)
        total_pages = len(reader.pages)
        set_runtime_page_count(total_pages)
        if total_pages == 0:
            raise ValueError(f"PDF has no pages: {file_name}")
        return reader, total_pages

    def parse_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        track: str,
        pdf_reader_factory: PdfReaderFactory,
        set_runtime_page_count: SetRuntimePageCountFn,
        pdf_parse_runtime: Any,
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
        source_cache_identity: str = "",
        last_figure_blocks: Any = None,
        parse_pdf_with_ocr: ParsePdfWithOcrFn,
        current_stats: Optional[Dict[str, Any]] = None,
        get_current_stats: Optional[GetCurrentStatsFn] = None,
        build_pdf_runtime_state: BuildPdfRuntimeStateFn,
        apply_state_update: ApplyStateUpdateFn,
    ) -> ParseResult:
        reader, total_pages = self.prepare_pdf_reader(
            file_name=file_name,
            file_bytes=file_bytes,
            pdf_reader_factory=pdf_reader_factory,
            set_runtime_page_count=set_runtime_page_count,
        )
        runtime_outcome = pdf_parse_runtime.parse_pdf(
            file_name=file_name,
            file_bytes=file_bytes,
            track=track,
            reader=reader,
            total_pages=total_pages,
            source_cache_identity=source_cache_identity,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
            last_figure_blocks=last_figure_blocks,
            parse_pdf_with_ocr=parse_pdf_with_ocr,
        )
        resolved_current_stats = dict(current_stats or {})
        if str(runtime_outcome.get("kind") or "") == "visual_result" and callable(get_current_stats):
            resolved_current_stats = dict(get_current_stats() or {})
        state_update = build_pdf_runtime_state(
            runtime_outcome=runtime_outcome,
            current_stats=resolved_current_stats,
        )
        result = apply_state_update(state_update)
        if result is None:
            raise ValueError("PDF state update returned no result.")
        return result

    def parse_pdf_visual_first(
        self,
        *,
        pdf_visual_parse_runtime: Any,
        file_name: str,
        file_bytes: bytes,
        reader: Any,
        page_count: int,
        layout_extractor: Any,
        vision: Any,
        set_last_mineru_run_meta: SetLastMineruRunMetaFn,
        build_visual_parse_state: BuildVisualParseStateFn,
        apply_state_update: ApplyStateUpdateFn,
        source_cache_identity: str = "",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Optional[ParseResult]:
        runtime_result = pdf_visual_parse_runtime.parse_pdf_visual_first(
            file_name=file_name,
            file_bytes=file_bytes,
            reader=reader,
            page_count=page_count,
            layout_extractor=layout_extractor,
            vision=vision,
            source_cache_identity=source_cache_identity,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
        )
        if runtime_result is None:
            return None
        set_last_mineru_run_meta(runtime_result.get("mineru_run_meta"))
        return apply_state_update(build_visual_parse_state(runtime_result.get("outcome") or {}))

    def parse_pdf_with_ocr(
        self,
        *,
        pdf_ocr_runtime: Any,
        file_bytes: bytes,
        page_count: int,
        set_last_figure_blocks: SetLastFigureBlocksFn,
        cue_pages: List[int] | None = None,
    ) -> ParseResult:
        markdown, bbox_map, table_blocks, figure_blocks = pdf_ocr_runtime.parse_pdf_with_ocr(
            file_bytes=file_bytes,
            page_count=page_count,
            cue_pages=cue_pages,
        )
        set_last_figure_blocks(figure_blocks)
        return markdown, bbox_map, table_blocks


class ParserPdfBootstrapRuntime:
    """Build PDF OCR/native runtimes so parser.py only keeps phase sequencing."""

    def build_pdf_runtime_attrs(
        self,
        *,
        parser_dependency_bundle_runtime: Any,
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
        max_pages: int,
        max_pages_visual: int,
        visual_probe_pages: int,
        native_text_threshold: int,
        ocr_cue_scan_pages: int,
        enable_fitz_table: bool,
        table_merge_enable: bool,
        visual_force_ocr_on_weak_native: bool,
        gemini_vision_enable_figures: bool,
        get_ocr_engine: RuntimeCallback,
        set_runtime_page_count: RuntimeCallback,
        normalize_text: RuntimeCallback,
        split_page_text: RuntimeCallback,
        build_ocr_page_indices: RuntimeCallback,
        looks_like_table_cue_text: RuntimeCallback,
        infer_tables_from_ocr_cells: RuntimeCallback,
        augment_with_line_tables: RuntimeCallback,
        need_line_table_augmentation: RuntimeCallback,
        select_line_augmentation_pages: RuntimeCallback,
        infer_tables_from_page_lines: RuntimeCallback,
        select_uncovered_table_like_pages: RuntimeCallback,
        infer_figures_from_page_lines: RuntimeCallback,
        get_last_figure_blocks: RuntimeCallback,
        enhance_low_quality_pages_with_gemini_vision: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        prune_fragment_tables: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
        collect_table_cue_pages: RuntimeCallback,
        extract_pdf_tables_with_fitz: RuntimeCallback,
        is_weak_native_table_result: RuntimeCallback,
        figure_blocks_need_vision: RuntimeCallback,
    ) -> Dict[str, Any]:
        pdf_ocr_bundle = parser_dependency_bundle_runtime.build_pdf_ocr_bundle(
            ocr_large_doc_dpi=ocr_large_doc_dpi,
            ocr_large_doc_page_threshold=ocr_large_doc_page_threshold,
            ocr_low_priority_dpi=ocr_low_priority_dpi,
            ocr_high_priority_pages=ocr_high_priority_pages,
            ocr_dense_cue_threshold=ocr_dense_cue_threshold,
            ocr_max_attempt_pages_dense_cue=ocr_max_attempt_pages_dense_cue,
            ocr_max_attempt_pages_mid_cue=ocr_max_attempt_pages_mid_cue,
            ocr_dynamic_neighbor_pages=ocr_dynamic_neighbor_pages,
            ocr_dynamic_neighbor_auto_enable=ocr_dynamic_neighbor_auto_enable,
            ocr_dynamic_neighbor_auto_max=ocr_dynamic_neighbor_auto_max,
            ocr_min_pages_before_budget=ocr_min_pages_before_budget,
            ocr_front_scan_pages=ocr_front_scan_pages,
            ocr_low_cue_boost_enable=ocr_low_cue_boost_enable,
            ocr_low_cue_min_pages_cap=ocr_low_cue_min_pages_cap,
            ocr_time_budget_max_sec=ocr_time_budget_max_sec,
            ocr_time_budget_sec=ocr_time_budget_sec,
            ocr_time_budget_per_page=ocr_time_budget_per_page,
            ocr_budget_guard_ratio=ocr_budget_guard_ratio,
            ocr_dynamic_early_stop_enable=ocr_dynamic_early_stop_enable,
            ocr_dynamic_early_stop_min_pages=ocr_dynamic_early_stop_min_pages,
            ocr_dynamic_early_stop_min_signal_pages=ocr_dynamic_early_stop_min_signal_pages,
            ocr_dynamic_early_stop_streak=ocr_dynamic_early_stop_streak,
            ocr_relaxed_trigger_table_count=ocr_relaxed_trigger_table_count,
            ocr_table_relaxed_min_quality=ocr_table_relaxed_min_quality,
            ocr_table_min_quality=ocr_table_min_quality,
            ocr_uncovered_line_aug_pages=ocr_uncovered_line_aug_pages,
            get_ocr_engine=get_ocr_engine,
            set_runtime_page_count=set_runtime_page_count,
            normalize_text=normalize_text,
            normalize_box=VisualBboxRuntime.normalize_ocr_box,
            build_ocr_page_indices=build_ocr_page_indices,
            looks_like_table_cue_text=looks_like_table_cue_text,
            infer_tables_from_ocr_cells=infer_tables_from_ocr_cells,
            augment_with_line_tables=augment_with_line_tables,
            need_line_table_augmentation=need_line_table_augmentation,
            select_line_augmentation_pages=select_line_augmentation_pages,
            infer_tables_from_page_lines=infer_tables_from_page_lines,
            select_uncovered_table_like_pages=select_uncovered_table_like_pages,
            infer_figures_from_page_lines=infer_figures_from_page_lines,
            get_last_figure_blocks=get_last_figure_blocks,
            enhance_low_quality_pages_with_gemini_vision=enhance_low_quality_pages_with_gemini_vision,
            merge_figure_blocks=merge_figure_blocks,
            prune_fragment_tables=prune_fragment_tables,
        )
        pdf_ocr_runtime = PdfOcrRuntime(
            **pdf_ocr_bundle.config_kwargs,
            **pdf_ocr_bundle.callback_kwargs,
        )

        pdf_native_bundle = parser_dependency_bundle_runtime.build_pdf_native_bundle(
            max_pages=max_pages,
            max_pages_visual=max_pages_visual,
            visual_probe_pages=visual_probe_pages,
            native_text_threshold=native_text_threshold,
            ocr_cue_scan_pages=ocr_cue_scan_pages,
            enable_fitz_table=enable_fitz_table,
            table_merge_enable=table_merge_enable,
            visual_force_ocr_on_weak_native=visual_force_ocr_on_weak_native,
            gemini_vision_enable_figures=gemini_vision_enable_figures,
            normalize_text=normalize_text,
            split_page_text=split_page_text,
            append_ref=ReferenceRuntime.append_ref,
            collect_table_cue_pages=collect_table_cue_pages,
            extract_pdf_tables_with_fitz=extract_pdf_tables_with_fitz,
            is_weak_native_table_result=is_weak_native_table_result,
            select_line_augmentation_pages=select_line_augmentation_pages,
            infer_tables_from_page_lines=infer_tables_from_page_lines,
            augment_with_line_tables=augment_with_line_tables,
            merge_same_page_tables=merge_same_page_tables,
            merge_cross_page_tables=merge_cross_page_tables,
            infer_figures_from_page_lines=infer_figures_from_page_lines,
            figure_blocks_need_vision=figure_blocks_need_vision,
            enhance_low_quality_pages_with_gemini_vision=enhance_low_quality_pages_with_gemini_vision,
            merge_figure_blocks=merge_figure_blocks,
            prune_fragment_tables=prune_fragment_tables,
        )
        pdf_native_parse_runtime = PdfNativeParseRuntime(
            **pdf_native_bundle.config_kwargs,
            **pdf_native_bundle.callback_kwargs,
        )

        return {
            "_pdf_ocr_runtime": pdf_ocr_runtime,
            "_pdf_native_parse_runtime": pdf_native_parse_runtime,
        }
