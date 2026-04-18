from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


class ParserInitializationRuntime:
    def initialize(
        self,
        *,
        parser: Any,
        max_pages: int | None,
        text_extensions: Set[str],
        image_extensions: Set[str],
        limit_env_value: Callable[..., int],
    ) -> None:
        mineru_layout_extractor_factory = getattr(parser, "_mineru_layout_extractor_factory", None)
        if mineru_layout_extractor_factory is None:
            from ..integration.mineru_layout import MineruLayoutExtractor

            mineru_layout_extractor_factory = MineruLayoutExtractor
        roi_cropper_factory = getattr(parser, "_roi_cropper_factory", None)
        if roi_cropper_factory is None:
            from ..visual.roi_cropper import RoiCropper

            roi_cropper_factory = RoiCropper
        visual_vision_extractor_factory = getattr(parser, "_visual_vision_extractor_factory", None)
        if visual_vision_extractor_factory is None:
            from ..visual.vision_extractor import GeminiVisionExtractor

            visual_vision_extractor_factory = GeminiVisionExtractor

        module2_root = Path(__file__).resolve().parents[2]
        repo_root = module2_root.parents[3]
        module2_cache_root = (module2_root / ".cache").resolve()
        for attr_name, runtime_value in parser._parser_bootstrap_runtime.build_support_runtime_attrs(
            getenv=parser._getenv,
            limit_env_value=limit_env_value,
            module2_root=module2_root,
            repo_root=repo_root,
        ).items():
            setattr(parser, attr_name, runtime_value)
        parser._parser_provider_state_runtime = parser._parser_bootstrap_runtime.build_provider_state_runtime(
            mineru_layout_extractor_factory=mineru_layout_extractor_factory,
            build_mineru_layout_kwargs=parser._mineru_layout_extractor_kwargs,
            roi_cropper_factory=roi_cropper_factory,
            build_roi_cropper_kwargs=parser._roi_cropper_kwargs,
            visual_vision_extractor_factory=visual_vision_extractor_factory,
            build_visual_vision_kwargs=parser._visual_vision_extractor_kwargs,
        )

        self._init_core_parse_config(
            parser=parser,
            module2_cache_root=module2_cache_root,
            max_pages_override=max_pages,
        )
        self._init_ocr_table_limits(parser=parser)
        self._init_docx_media_config(parser=parser)
        self._init_table_merge_and_vision_config(parser=parser)
        self._init_visual_mineru_config(
            parser=parser,
            module2_cache_root=module2_cache_root,
        )
        self._init_document_table_runtimes(parser=parser)
        self._init_semantic_vision_runtimes(parser=parser)
        self._init_pdf_image_runtimes(parser=parser)
        self._init_visual_pipeline_runtimes(parser=parser, image_extensions=image_extensions)
        self._init_docx_dispatch_runtimes(
            parser=parser,
            text_extensions=text_extensions,
            image_extensions=image_extensions,
        )

    def _apply_config_values(self, *, parser: Any, config: Dict[str, Any]) -> None:
        for key, value in config.items():
            setattr(parser, key, value)

    def _init_core_parse_config(
        self,
        *,
        parser: Any,
        module2_cache_root: Path,
        max_pages_override: int | None,
    ) -> None:
        self._apply_config_values(
            parser=parser,
            config=parser._parser_config_runtime.build_core_parse_config(
                module2_cache_root=module2_cache_root,
                max_pages_override=max_pages_override,
            ),
        )
        parser.artifact_root_dir.mkdir(parents=True, exist_ok=True)

    def _init_ocr_table_limits(self, *, parser: Any) -> None:
        self._apply_config_values(
            parser=parser,
            config=parser._parser_config_runtime.build_ocr_table_limits(
                max_pages_visual=parser.max_pages_visual,
                visual_probe_pages=parser.visual_probe_pages,
            ),
        )

    def _init_docx_media_config(self, *, parser: Any) -> None:
        self._apply_config_values(
            parser=parser,
            config=parser._parser_config_runtime.build_docx_media_config(),
        )

    def _init_table_merge_and_vision_config(self, *, parser: Any) -> None:
        self._apply_config_values(
            parser=parser,
            config=parser._parser_config_runtime.build_table_merge_and_vision_config(
                max_pages_visual=parser.max_pages_visual,
                native_text_threshold=parser.native_text_threshold,
            ),
        )

    def _init_visual_mineru_config(
        self,
        *,
        parser: Any,
        module2_cache_root: Path,
    ) -> None:
        self._apply_config_values(
            parser=parser,
            config=parser._parser_config_runtime.build_visual_mineru_config(
                module2_cache_root=module2_cache_root,
            ),
        )

    def _init_document_table_runtimes(self, *, parser: Any) -> None:
        from ..visual.visual_planning_runtime import VisualTableCueRuntime
        from ..table.table_metadata import build_header_meta, decorate_rows_with_meta

        for attr_name, runtime_value in parser._parser_document_table_bootstrap_runtime.build_document_table_runtime_attrs(
            normalize_text=parser._normalize_text,
            normalize_token_for_compare=parser._normalize_token_for_compare,
            runtime_page_count_provider=parser._parser_run_state.runtime_page_count,
            decorate_rows_with_meta=decorate_rows_with_meta,
            build_header_meta=build_header_meta,
            table_max_rows=parser.table_max_rows,
            table_max_cols=parser.table_max_cols,
            xlsx_sheet_limit=parser.xlsx_sheet_limit,
            xlsx_cell_cap=parser.xlsx_cell_cap,
            table_merge_max_page_gap=parser.table_merge_max_page_gap,
            table_merge_header_sim=parser.table_merge_header_sim,
            table_merge_col_overlap=parser.table_merge_col_overlap,
            table_cell_cap=parser.table_cell_cap,
            table_merge_enable=parser.table_merge_enable,
            ocr_max_pages=parser.ocr_max_pages,
            ocr_front_scan_pages=parser.ocr_front_scan_pages,
            ocr_extra_sample_pages=parser.ocr_extra_sample_pages,
            ocr_cue_neighbor=parser.ocr_cue_neighbor,
            ocr_cue_max_pages=parser.ocr_cue_max_pages,
            ocr_max_scan_pages=parser.ocr_max_scan_pages,
            ocr_cue_boost_max_pages=parser.ocr_cue_boost_max_pages,
            ocr_min_coverage_ratio=parser.ocr_min_coverage_ratio,
            ocr_min_scan_pages=parser.ocr_min_scan_pages,
            visual_weak_table_min=parser.visual_weak_table_min,
            ocr_table_min_quality=parser.ocr_table_min_quality,
            ocr_line_aug_max_extra_cue_pages=parser.ocr_line_aug_max_extra_cue_pages,
            ocr_uncovered_line_aug_pages=parser.ocr_uncovered_line_aug_pages,
            ocr_table_min_rows=parser.ocr_table_min_rows,
            ocr_table_row_gap=parser.ocr_table_row_gap,
            ocr_table_col_tol=parser.ocr_table_col_tol,
            looks_like_table_cue_text=VisualTableCueRuntime.looks_like_table_cue_text,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_semantic_vision_runtimes(self, *, parser: Any) -> None:
        from ..table.table_metadata import build_header_meta, decorate_rows_with_meta

        self._init_ocr_semantic_foundations(parser=parser)
        self._init_vision_transport_foundations(parser=parser)
        for attr_name, runtime_value in parser._parser_visual_payload_bootstrap_runtime.build_visual_payload_runtime_attrs(
            parser_visual_payload_bundle_runtime=parser._parser_visual_payload_bundle_runtime,
            normalize_text=parser._normalize_text,
            normalize_token_for_compare=parser._normalize_token_for_compare,
            content_normalization_runtime=parser._content_normalization_runtime,
            figure_text_runtime=parser._figure_text_runtime,
            figure_inference=parser._figure_inference,
            figure_text_is_low_signal=parser._figure_text_runtime.figure_text_is_low_signal,
            table_header=parser._table_header,
            looks_like_false_table=parser._looks_like_false_table,
            gemini_vision_enable_figures=parser.gemini_vision_enable_figures,
            gemini_vision_max_figures_per_page=parser.gemini_vision_max_figures_per_page,
            gemini_vision_min_figure_quality=parser.gemini_vision_min_figure_quality,
            gemini_vision_max_tables_per_page=parser.gemini_vision_max_tables_per_page,
            gemini_vision_max_pages=parser.gemini_vision_max_pages,
            gemini_vision_min_table_quality=parser.gemini_vision_min_table_quality,
            table_max_cols=parser.table_max_cols,
            table_max_rows=parser.table_max_rows,
            table_cell_cap=parser.table_cell_cap,
            ocr_table_min_rows=parser.ocr_table_min_rows,
            ocr_cue_max_pages=parser.ocr_cue_max_pages,
            visual_weak_table_min=parser.visual_weak_table_min,
            visual_weak_table_quality=parser.visual_weak_table_quality,
            visual_use_table_html_fallback=parser.visual_use_table_html_fallback,
            decorate_rows_with_meta=decorate_rows_with_meta,
            build_header_meta=build_header_meta,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_ocr_semantic_foundations(self, *, parser: Any) -> None:
        from ..table.table_metadata import build_header_meta, decorate_rows_with_meta

        for attr_name, runtime_value in parser._parser_semantic_bootstrap_runtime.build_semantic_runtime_attrs(
            parser_ocr_table_inference_bundle_runtime=parser._parser_ocr_table_inference_bundle_runtime,
            parser_semantic_foundation_bundle_runtime=parser._parser_semantic_foundation_bundle_runtime,
            ocr_table_min_quality=parser.ocr_table_min_quality,
            ocr_table_min_cols=parser.ocr_table_min_cols,
            ocr_table_min_rows=parser.ocr_table_min_rows,
            ocr_table_row_tol=parser.ocr_table_row_tol,
            ocr_table_row_gap=parser.ocr_table_row_gap,
            ocr_table_col_tol=parser.ocr_table_col_tol,
            ocr_table_relaxed_row_gap_scale=parser.ocr_table_relaxed_row_gap_scale,
            ocr_table_relaxed_align_min=parser.ocr_table_relaxed_align_min,
            ocr_table_relaxed_overlap_min=parser.ocr_table_relaxed_overlap_min,
            ocr_table_relaxed_col_diff_max=parser.ocr_table_relaxed_col_diff_max,
            table_max_rows=parser.table_max_rows,
            table_max_cols=parser.table_max_cols,
            table_cell_cap=parser.table_cell_cap,
            table_merge_enable=parser.table_merge_enable,
            gemini_vision_enable_figures=parser.gemini_vision_enable_figures,
            runtime_page_count_provider=parser._parser_run_state.runtime_page_count,
            infer_headers_and_data_rows=parser._table_header.infer_headers_and_data_rows,
            drop_redundant_header_like_rows=parser._table_header.drop_redundant_header_like_rows,
            decorate_rows_with_meta=decorate_rows_with_meta,
            build_header_meta=build_header_meta,
            looks_like_false_table=parser._looks_like_false_table,
            merge_same_page_tables=parser._table_merge_runtime.merge_same_page_tables,
            merge_cross_page_tables=parser._table_merge_runtime.merge_cross_page_tables,
            normalize_text=parser._normalize_text,
            normalize_token_for_compare=parser._normalize_token_for_compare,
            group_table_rows=parser._ocr_table_utils.group_table_rows,
            split_group_by_row_gaps=parser._ocr_table_utils.split_group_by_row_gaps,
            expand_group_with_sparse_rows=parser._ocr_table_utils.expand_group_with_sparse_rows,
            table_quality_score=parser._ocr_table_utils.table_quality_score,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_vision_transport_foundations(self, *, parser: Any) -> None:
        from ...integrations.llm.provider import resolve_llm_native_api_url

        for attr_name, runtime_value in parser._parser_vision_transport_bootstrap_runtime.build_vision_transport_runtime_attrs(
            parser_vision_bundle_runtime=parser._parser_vision_bundle_runtime,
            resolve_native_api_url=resolve_llm_native_api_url,
            user_agent="smart-doc-flow-module2-parser/1.0",
            default_model="gemini-3.1-pro-preview",
            normalize_text=parser._normalize_text,
            normalize_token_for_compare=parser._normalize_token_for_compare,
            gemini_vision_dpi=parser.gemini_vision_dpi,
            gemini_vision_max_side_px=parser.gemini_vision_max_side_px,
            gemini_vision_model=parser.gemini_vision_model,
            gemini_vision_timeout_sec=parser.gemini_vision_timeout_sec,
            gemini_vision_max_output_tokens=parser.gemini_vision_max_output_tokens,
            gemini_native_fallback_enabled=parser.gemini_native_fallback_enabled,
            resolve_api_key=parser._gemini_api_key,
            resolve_native_api_key=parser._gemini_native_api_key,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_pdf_image_runtimes(self, *, parser: Any) -> None:
        from ..visual.visual_planning_runtime import VisualTableCueRuntime

        for attr_name, runtime_value in parser._parser_pdf_bootstrap_runtime.build_pdf_runtime_attrs(
            parser_dependency_bundle_runtime=parser._parser_dependency_bundle_runtime,
            ocr_large_doc_dpi=parser.ocr_large_doc_dpi,
            ocr_large_doc_page_threshold=parser.ocr_large_doc_page_threshold,
            ocr_low_priority_dpi=parser.ocr_low_priority_dpi,
            ocr_high_priority_pages=parser.ocr_high_priority_pages,
            ocr_dense_cue_threshold=parser.ocr_dense_cue_threshold,
            ocr_max_attempt_pages_dense_cue=parser.ocr_max_attempt_pages_dense_cue,
            ocr_max_attempt_pages_mid_cue=parser.ocr_max_attempt_pages_mid_cue,
            ocr_dynamic_neighbor_pages=parser.ocr_dynamic_neighbor_pages,
            ocr_dynamic_neighbor_auto_enable=parser.ocr_dynamic_neighbor_auto_enable,
            ocr_dynamic_neighbor_auto_max=parser.ocr_dynamic_neighbor_auto_max,
            ocr_min_pages_before_budget=parser.ocr_min_pages_before_budget,
            ocr_front_scan_pages=parser.ocr_front_scan_pages,
            ocr_low_cue_boost_enable=parser.ocr_low_cue_boost_enable,
            ocr_low_cue_min_pages_cap=parser.ocr_low_cue_min_pages_cap,
            ocr_time_budget_max_sec=parser.ocr_time_budget_max_sec,
            ocr_time_budget_sec=parser.ocr_time_budget_sec,
            ocr_time_budget_per_page=parser.ocr_time_budget_per_page,
            ocr_budget_guard_ratio=parser.ocr_budget_guard_ratio,
            ocr_dynamic_early_stop_enable=parser.ocr_dynamic_early_stop_enable,
            ocr_dynamic_early_stop_min_pages=parser.ocr_dynamic_early_stop_min_pages,
            ocr_dynamic_early_stop_min_signal_pages=parser.ocr_dynamic_early_stop_min_signal_pages,
            ocr_dynamic_early_stop_streak=parser.ocr_dynamic_early_stop_streak,
            ocr_relaxed_trigger_table_count=parser.ocr_relaxed_trigger_table_count,
            ocr_table_relaxed_min_quality=parser.ocr_table_relaxed_min_quality,
            ocr_table_min_quality=parser.ocr_table_min_quality,
            ocr_uncovered_line_aug_pages=parser.ocr_uncovered_line_aug_pages,
            max_pages=parser.max_pages,
            max_pages_visual=parser.max_pages_visual,
            visual_probe_pages=parser.visual_probe_pages,
            native_text_threshold=parser.native_text_threshold,
            ocr_cue_scan_pages=parser.ocr_cue_scan_pages,
            enable_fitz_table=parser.enable_fitz_table,
            table_merge_enable=parser.table_merge_enable,
            visual_force_ocr_on_weak_native=parser.visual_force_ocr_on_weak_native,
            gemini_vision_enable_figures=parser.gemini_vision_enable_figures,
            get_ocr_engine=parser._get_ocr_engine,
            set_runtime_page_count=parser._parser_run_state.set_runtime_page_count,
            normalize_text=parser._normalize_text,
            split_page_text=parser._split_page_text,
            build_ocr_page_indices=parser._ocr_table_utils.build_ocr_page_indices,
            looks_like_table_cue_text=VisualTableCueRuntime.looks_like_table_cue_text,
            infer_tables_from_ocr_cells=parser._ocr_table_inference.infer_tables_from_ocr_cells,
            augment_with_line_tables=parser._ocr_table_utils.augment_with_line_tables,
            need_line_table_augmentation=parser._ocr_table_utils.need_line_table_augmentation,
            select_line_augmentation_pages=parser._ocr_table_utils.select_line_augmentation_pages,
            infer_tables_from_page_lines=parser._ocr_table_inference.infer_tables_from_page_lines,
            select_uncovered_table_like_pages=parser._ocr_table_utils.select_uncovered_table_like_pages,
            infer_figures_from_page_lines=parser._figure_inference.infer_figures_from_page_lines,
            get_last_figure_blocks=parser._parser_run_state.peek_last_figure_blocks,
            enhance_low_quality_pages_with_gemini_vision=parser._enhance_low_quality_pages_with_gemini_vision,
            merge_figure_blocks=parser._figure_inference.merge_figure_blocks,
            prune_fragment_tables=parser._table_pruning_runtime.prune_fragment_tables,
            merge_same_page_tables=parser._table_merge_runtime.merge_same_page_tables,
            merge_cross_page_tables=parser._table_merge_runtime.merge_cross_page_tables,
            collect_table_cue_pages=parser._visual_table_cue_runtime.collect_table_cue_pages,
            extract_pdf_tables_with_fitz=parser._pdf_fitz_table_runtime.extract_pdf_tables_with_fitz,
            is_weak_native_table_result=parser._visual_table_cue_runtime.is_weak_native_table_result,
            figure_blocks_need_vision=parser._figure_inference.figure_blocks_need_vision,
        ).items():
            setattr(parser, attr_name, runtime_value)
        self._init_image_parse_runtimes(parser=parser)

    def _init_image_parse_runtimes(self, *, parser: Any) -> None:
        for attr_name, runtime_value in parser._parser_image_bootstrap_runtime.build_image_runtime_attrs(
            parser_image_bundle_runtime=parser._parser_image_bundle_runtime,
            max_pages_visual=parser.max_pages_visual,
            enable_gemini_vision_enhance=parser.enable_gemini_vision_enhance,
            gemini_vision_max_pages=parser.gemini_vision_max_pages,
            gemini_vision_consecutive_fail_stop=parser.gemini_vision_consecutive_fail_stop,
            set_runtime_page_count=parser._parser_run_state.set_runtime_page_count,
            visual_backend_available=parser._visual_backend_available,
            resolve_api_key=parser._gemini_api_key,
            get_ocr_engine=parser._get_ocr_engine,
            normalize_text=parser._normalize_text,
            select_low_quality_pages_for_vision=parser._visual_page_signal_runtime.select_low_quality_pages_for_vision,
            vision_focus_from_page_lines=parser._visual_page_signal_runtime.vision_focus_from_page_lines,
            render_page_png_for_vision=parser._vision_request_runtime.render_page_png_for_vision,
            extract_payload=parser._vision_request_runtime.extract_payload,
            extract_vision_insights=parser._vision_response_runtime.extract_vision_insights,
            build_tables_from_vision_payload=parser._table_vision_payload.build_tables_from_vision_payload,
            build_figures_from_vision_payload=parser._figure_vision_payload.build_figures_from_vision_payload,
            infer_tables_from_ocr_cells=parser._ocr_table_inference.infer_tables_from_ocr_cells,
            infer_tables_from_page_lines=parser._ocr_table_inference.infer_tables_from_page_lines,
            infer_figures_from_page_lines=parser._figure_inference.infer_figures_from_page_lines,
            enhance_low_quality_pages_with_gemini_vision=parser._enhance_low_quality_pages_with_gemini_vision,
            merge_figure_blocks=parser._figure_inference.merge_figure_blocks,
            augment_with_line_tables=parser._ocr_table_utils.augment_with_line_tables,
            prune_fragment_tables=parser._table_pruning_runtime.prune_fragment_tables,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_visual_pipeline_runtimes(self, *, parser: Any, image_extensions: Set[str]) -> None:
        from ..visual.visual_planning_runtime import VisualTableCueRuntime

        for attr_name, runtime_value in parser._parser_visual_context_bootstrap_runtime.build_visual_context_runtime_attrs(
            parser_visual_context_bundle_runtime=parser._parser_visual_context_bundle_runtime,
            image_extensions=image_extensions,
            native_text_threshold=parser.native_text_threshold,
            visual_probe_pages=parser.visual_probe_pages,
            mineru_method=parser.mineru_method,
            mineru_scanned_method=parser.mineru_scanned_method,
            mineru_method_fallbacks=parser.mineru_method_fallbacks,
            visual_first_max_pages_scanned=parser.visual_first_max_pages_scanned,
            mineru_text_first_office_pdf_enable=parser.mineru_text_first_office_pdf_enable,
            mineru_text_first_office_pdf_min_pages=parser.mineru_text_first_office_pdf_min_pages,
            mineru_text_first_office_pdf_min_probe_chars=parser.mineru_text_first_office_pdf_min_probe_chars,
            pdf_text_first_enable=parser.pdf_text_first_enable,
            pdf_text_heavy_min_probe_chars=parser.pdf_text_heavy_min_probe_chars,
            pdf_text_heavy_min_chars_per_page=parser.pdf_text_heavy_min_chars_per_page,
            pdf_text_heavy_max_visual_cues=parser.pdf_text_heavy_max_visual_cues,
            pdf_mixed_text_pref_min_chars_per_page=parser.pdf_mixed_text_pref_min_chars_per_page,
            pdf_mixed_text_pref_max_visual_cues=parser.pdf_mixed_text_pref_max_visual_cues,
            pdf_text_only_short_circuit_enable=parser.pdf_text_only_short_circuit_enable,
            visual_max_objects=parser.visual_max_objects,
            visual_table_max_per_page=parser.visual_table_max_per_page,
            visual_figure_max_per_page=parser.visual_figure_max_per_page,
            visual_figure_chart_score_min=parser.visual_figure_chart_score_min,
            visual_figure_cueless_fallback_max=parser.visual_figure_cueless_fallback_max,
            visual_figure_refine_budget=parser.visual_figure_refine_budget,
            visual_figure_refine_min_score=parser.visual_figure_refine_min_score,
            visual_runtime_large_doc_page_threshold=parser.visual_runtime_large_doc_page_threshold,
            visual_runtime_large_doc_image_threshold=parser.visual_runtime_large_doc_image_threshold,
            visual_runtime_large_doc_max_objects=parser.visual_runtime_large_doc_max_objects,
            visual_runtime_large_doc_figure_max_per_page=parser.visual_runtime_large_doc_figure_max_per_page,
            visual_runtime_large_doc_cueless_fallback_max=parser.visual_runtime_large_doc_cueless_fallback_max,
            visual_runtime_large_doc_chart_score_min=parser.visual_runtime_large_doc_chart_score_min,
            visual_runtime_large_doc_refine_budget=parser.visual_runtime_large_doc_refine_budget,
            visual_runtime_extreme_doc_page_threshold=parser.visual_runtime_extreme_doc_page_threshold,
            visual_runtime_extreme_doc_max_objects=parser.visual_runtime_extreme_doc_max_objects,
            visual_runtime_extreme_doc_figure_max_per_page=parser.visual_runtime_extreme_doc_figure_max_per_page,
            visual_runtime_extreme_doc_cueless_fallback_max=parser.visual_runtime_extreme_doc_cueless_fallback_max,
            visual_runtime_extreme_doc_chart_score_min=parser.visual_runtime_extreme_doc_chart_score_min,
            visual_runtime_extreme_doc_refine_budget=parser.visual_runtime_extreme_doc_refine_budget,
            visual_first_max_pages=parser.visual_first_max_pages,
            max_pages=parser.max_pages,
            visual_runtime_office_text_layout_page_cap=parser.visual_runtime_office_text_layout_page_cap,
            visual_runtime_mixed_text_layout_page_cap=parser.visual_runtime_mixed_text_layout_page_cap,
            visual_runtime_extreme_doc_layout_page_cap=parser.visual_runtime_extreme_doc_layout_page_cap,
            visual_context_max_chars=parser.visual_context_max_chars,
            visual_figure_chart_only=parser.visual_figure_chart_only,
            visual_figure_allow_cueless_fallback=parser.visual_figure_allow_cueless_fallback,
            normalize_text=parser._normalize_text,
            split_page_text=parser._split_page_text,
            safe_text_list=parser._content_normalization_runtime.safe_text_list,
            infer_figure_type_from_text=parser._figure_inference.infer_figure_type_from_text,
            looks_like_figure_cue_text=parser._figure_inference.looks_like_figure_cue_text,
        ).items():
            setattr(parser, attr_name, runtime_value)
        for attr_name, runtime_value in parser._parser_visual_execution_bootstrap_runtime.build_visual_execution_runtime_attrs(
            parser_visual_execution_bundle_runtime=parser._parser_visual_execution_bundle_runtime,
            table_cell_cap=parser.table_cell_cap,
            visual_table_max_per_page=parser.visual_table_max_per_page,
            visual_figure_max_per_page=parser.visual_figure_max_per_page,
            visual_figure_refine_budget=parser.visual_figure_refine_budget,
            visual_figure_refine_min_score=parser.visual_figure_refine_min_score,
            visual_vision_concurrency=parser.visual_vision_concurrency,
            visual_text_only_min_chars=parser.visual_text_only_min_chars,
            table_merge_enable=parser.table_merge_enable,
            enable_mineru_layout=parser.enable_mineru_layout,
            pipeline_mode=parser.pipeline_mode,
            visual_first_allow_legacy_fallback=parser.visual_first_allow_legacy_fallback,
            build_visual_object_context=parser._visual_object_context_runtime.build_visual_object_context,
            get_cropper=parser._parser_provider_state_runtime.get_roi_cropper,
            build_table_from_visual_payload=parser._visual_table_builder.build_table_from_visual_payload,
            table_payload_has_content=lambda payload: parser._figure_inference.table_payload_has_content(
                payload,
                table_max_cols=parser.table_max_cols,
            ),
            build_figure_from_visual_payload=parser._visual_figure_builder.build_figure_from_visual_payload,
            figure_payload_has_content=parser._figure_inference.figure_payload_has_content,
            build_visual_parse_status_fields=lambda **kwargs: parser._visual_status_builder_runtime.build_status_fields(
                **kwargs,
                mineru_run_meta=parser._parser_run_state.get_last_mineru_run_meta(),
            ),
            merge_same_page_tables=parser._table_merge_runtime.merge_same_page_tables,
            merge_cross_page_tables=parser._table_merge_runtime.merge_cross_page_tables,
            prune_fragment_tables=parser._table_pruning_runtime.prune_fragment_tables,
            merge_figure_blocks=parser._figure_inference.merge_figure_blocks,
            normalize_text=parser._normalize_text,
            split_page_text=parser._split_page_text,
            bootstrap=parser._visual_pdf_bootstrap_runtime.bootstrap,
            prepare_context=parser._visual_pdf_prepare_runtime.prepare_context,
            build_initial_refs=parser._visual_pdf_prepare_runtime.build_initial_refs,
            prioritize_layout_objects=parser._visual_layout_selector_runtime.prioritize_layout_objects,
            extract_native_tables_with_fitz=(
                (lambda **kwargs: parser._pdf_fitz_table_runtime.extract_pdf_tables_with_fitz(
                    merge_tables=False,
                    **kwargs,
                ))
                if parser.enable_fitz_table
                else None
            ),
            parse_pdf_visual_first=parser._parse_pdf_visual_first,
            visual_backend_available=parser._visual_backend_available,
            parse_pdf_native=parser._pdf_native_parse_runtime.parse_pdf_native,
            get_last_mineru_run_meta=parser._parser_run_state.get_last_mineru_run_meta,
        ).items():
            setattr(parser, attr_name, runtime_value)

    def _init_docx_dispatch_runtimes(
        self,
        *,
        parser: Any,
        text_extensions: Set[str],
        image_extensions: Set[str],
    ) -> None:
        from ..format.office_pdf import convert_word_bytes_to_pdf
        from ..table.table_metadata import build_header_meta, decorate_rows_with_meta

        for attr_name, runtime_value in parser._parser_docx_bootstrap_runtime.build_docx_runtime_attrs(
            parser_dispatch_bundle_runtime=parser._parser_dispatch_bundle_runtime,
            parser_docx_content_bundle_runtime=parser._parser_docx_content_bundle_runtime,
            build_docx_enrichment_bundle=parser._parser_dependency_bundle_runtime.build_docx_enrichment_bundle,
            word_pdf_timeout_sec=parser.word_pdf_timeout_sec,
            word_pdf_parse_use_source_signals=parser.word_pdf_parse_use_source_signals,
            word_pdf_docx_chart_xml_merge_enable=parser.word_pdf_docx_chart_xml_merge_enable,
            word_parse_via_pdf=parser.word_parse_via_pdf,
            office_convert_enabled=parser.office_convert_enabled,
            word_convert_allow_native_fallback=parser.word_convert_allow_native_fallback,
            text_extensions=text_extensions,
            image_extensions=image_extensions,
            artifact_root_dir=parser.artifact_root_dir,
            docx_chart_xml_enable=parser.docx_chart_xml_enable,
            docx_media_probe_enable=parser.docx_media_probe_enable,
            docx_media_max_assets=parser.docx_media_max_assets,
            docx_media_vision_enable=parser.docx_media_vision_enable,
            docx_media_nested_gemini_enhance_enable=parser.docx_media_nested_gemini_enhance_enable,
            docx_media_max_assets_unbounded=parser.docx_media_max_assets_unbounded,
            docx_media_vision_max_assets=parser.docx_media_vision_max_assets,
            docx_media_vision_max_assets_unbounded=parser.docx_media_vision_max_assets_unbounded,
            docx_media_vision_max_bytes=parser.docx_media_vision_max_bytes,
            docx_media_vision_chart_only=parser.docx_media_vision_chart_only,
            docx_media_vision_allow_noncue=parser.docx_media_vision_allow_noncue,
            nonpdf_figure_max=parser.nonpdf_figure_max,
            normalize_text=parser._normalize_text,
            safe_text_list=parser._content_normalization_runtime.safe_text_list,
            looks_like_figure_cue_text=parser._figure_inference.looks_like_figure_cue_text,
            normalize_dataframe_headers=parser._content_normalization_runtime.normalize_dataframe_headers,
            normalize_dataframe_matrix=parser._content_normalization_runtime.normalize_dataframe_matrix,
            decorate_rows_with_meta=decorate_rows_with_meta,
            build_header_meta=build_header_meta,
            parse_pdf=parser._parse_pdf,
            parse_docx_via_pdf=parser._parse_docx_via_pdf,
            parse_docx=parser._parse_docx,
            parse_xlsx=parser._parse_xlsx,
            parse_plain=parser._parse_plain,
            parse_image=parser._parse_image,
            get_last_figure_blocks=parser._parser_run_state.get_last_figure_blocks,
            set_last_figure_blocks=parser._parser_run_state.set_last_figure_blocks,
            convert_word_bytes_to_pdf=convert_word_bytes_to_pdf,
            consume_document=parser._docx_parse_runtime.consume_document,
            merge_figure_blocks=parser._figure_inference.merge_figure_blocks,
            consume_relaxed_root=parser._docx_parse_runtime.consume_relaxed_root,
            append_text_ref=parser._nonpdf_text_runtime.append_text_ref,
            find_matching_pdf_figure_index=parser._figure_matching_runtime.find_matching_pdf_figure_index,
            table_block_to_dataframe=parser._content_normalization_runtime.table_block_to_dataframe,
        ).items():
            setattr(parser, attr_name, runtime_value)
