from __future__ import annotations

from typing import Any, Callable, Dict

from ..pipeline.block_index_runtime import BlockIndexRuntime
from ..schema.content_normalization_runtime import ContentNormalizationRuntime
from ..visual.figure_inference import FigureInferenceRuntime
from ..visual.figure_semantics import FigureTextRuntime
from ..table.ocr_table_inference import OcrTableInferenceRuntime
from ..table.ocr_table_utils import OcrTableUtils
from ..table.table_header_runtime import TableHeaderRuntime
from ..table.table_pruning_runtime import TablePruningRuntime


RuntimeCallback = Callable[..., Any]


class ParserOcrTableInferenceBundleRuntime:
    """Build pure kwargs for OCR table inference runtime wiring."""

    def build_threshold_kwargs(
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
    ) -> Dict[str, Any]:
        return {
            "ocr_table_min_quality": ocr_table_min_quality,
            "ocr_table_min_cols": ocr_table_min_cols,
            "ocr_table_min_rows": ocr_table_min_rows,
            "ocr_table_row_tol": ocr_table_row_tol,
            "ocr_table_row_gap": ocr_table_row_gap,
            "ocr_table_col_tol": ocr_table_col_tol,
            "ocr_table_relaxed_row_gap_scale": ocr_table_relaxed_row_gap_scale,
            "ocr_table_relaxed_align_min": ocr_table_relaxed_align_min,
            "ocr_table_relaxed_overlap_min": ocr_table_relaxed_overlap_min,
            "ocr_table_relaxed_col_diff_max": ocr_table_relaxed_col_diff_max,
            "table_max_rows": table_max_rows,
            "table_max_cols": table_max_cols,
            "table_cell_cap": table_cell_cap,
            "table_merge_enable": table_merge_enable,
        }

    def build_callback_kwargs(
        self,
        *,
        runtime_page_count_provider: RuntimeCallback,
        infer_headers_and_data_rows: RuntimeCallback,
        drop_redundant_header_like_rows: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        looks_like_false_table: RuntimeCallback,
        normalize_text: RuntimeCallback,
        contains_section_marker: RuntimeCallback,
        is_page_number_token: RuntimeCallback,
        dedupe_ocr_cells: RuntimeCallback,
        median_cell_height: RuntimeCallback,
        cluster_ocr_rows: RuntimeCallback,
        group_table_rows: RuntimeCallback,
        split_group_by_row_gaps: RuntimeCallback,
        build_col_anchors: RuntimeCallback,
        nearest_anchor_index: RuntimeCallback,
        expand_group_with_sparse_rows: RuntimeCallback,
        table_quality_score: RuntimeCallback,
        split_table_line: RuntimeCallback,
        is_table_line: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "runtime_page_count_provider": runtime_page_count_provider,
            "infer_headers_and_data_rows": infer_headers_and_data_rows,
            "drop_redundant_header_like_rows": drop_redundant_header_like_rows,
            "decorate_rows_with_meta": decorate_rows_with_meta,
            "build_header_meta": build_header_meta,
            "looks_like_false_table": looks_like_false_table,
            "normalize_text": normalize_text,
            "contains_section_marker": contains_section_marker,
            "is_page_number_token": is_page_number_token,
            "dedupe_ocr_cells": dedupe_ocr_cells,
            "median_cell_height": median_cell_height,
            "cluster_ocr_rows": cluster_ocr_rows,
            "group_table_rows": group_table_rows,
            "split_group_by_row_gaps": split_group_by_row_gaps,
            "build_col_anchors": build_col_anchors,
            "nearest_anchor_index": nearest_anchor_index,
            "expand_group_with_sparse_rows": expand_group_with_sparse_rows,
            "table_quality_score": table_quality_score,
            "split_table_line": split_table_line,
            "is_table_line": is_table_line,
            "merge_same_page_tables": merge_same_page_tables,
            "merge_cross_page_tables": merge_cross_page_tables,
        }


class ParserSemanticFoundationBundleRuntime:
    """Build pure kwargs for parser-owned semantic foundation runtimes."""

    def build_figure_text_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        header_token_is_generic: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "header_token_is_generic": header_token_is_generic,
        }

    def build_table_pruning_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        contains_section_marker: RuntimeCallback,
        header_token_is_generic: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "contains_section_marker": contains_section_marker,
            "header_token_is_generic": header_token_is_generic,
        }

    def build_figure_inference_kwargs(
        self,
        *,
        vision_enable_figures: bool,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        contains_figure_marker: RuntimeCallback,
        contains_catalog_marker: RuntimeCallback,
        strip_figure_caption_noise: RuntimeCallback,
        count_figure_markers_in_text: RuntimeCallback,
        next_figure_index: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_enable_figures": vision_enable_figures,
            "normalize_text": normalize_text,
            "normalize_token_for_compare": normalize_token_for_compare,
            "contains_figure_marker": contains_figure_marker,
            "contains_catalog_marker": contains_catalog_marker,
            "strip_figure_caption_noise": strip_figure_caption_noise,
            "count_figure_markers_in_text": count_figure_markers_in_text,
            "next_figure_index": next_figure_index,
        }

    def build_content_normalization_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
        }


class ParserSemanticBootstrapRuntime:
    """Build OCR/figure semantic runtimes so parser.py keeps only stage ordering."""

    def build_semantic_runtime_attrs(
        self,
        *,
        parser_ocr_table_inference_bundle_runtime: Any,
        parser_semantic_foundation_bundle_runtime: Any,
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
        vision_enable_figures: bool,
        runtime_page_count_provider: RuntimeCallback,
        infer_headers_and_data_rows: RuntimeCallback,
        drop_redundant_header_like_rows: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        looks_like_false_table: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        group_table_rows: RuntimeCallback,
        split_group_by_row_gaps: RuntimeCallback,
        expand_group_with_sparse_rows: RuntimeCallback,
        table_quality_score: RuntimeCallback,
    ) -> Dict[str, Any]:
        ocr_table_inference = OcrTableInferenceRuntime(
            **parser_ocr_table_inference_bundle_runtime.build_threshold_kwargs(
                ocr_table_min_quality=ocr_table_min_quality,
                ocr_table_min_cols=ocr_table_min_cols,
                ocr_table_min_rows=ocr_table_min_rows,
                ocr_table_row_tol=ocr_table_row_tol,
                ocr_table_row_gap=ocr_table_row_gap,
                ocr_table_col_tol=ocr_table_col_tol,
                ocr_table_relaxed_row_gap_scale=ocr_table_relaxed_row_gap_scale,
                ocr_table_relaxed_align_min=ocr_table_relaxed_align_min,
                ocr_table_relaxed_overlap_min=ocr_table_relaxed_overlap_min,
                ocr_table_relaxed_col_diff_max=ocr_table_relaxed_col_diff_max,
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                table_cell_cap=table_cell_cap,
                table_merge_enable=table_merge_enable,
            ),
            **parser_ocr_table_inference_bundle_runtime.build_callback_kwargs(
                runtime_page_count_provider=runtime_page_count_provider,
                infer_headers_and_data_rows=infer_headers_and_data_rows,
                drop_redundant_header_like_rows=drop_redundant_header_like_rows,
                decorate_rows_with_meta=decorate_rows_with_meta,
                build_header_meta=build_header_meta,
                looks_like_false_table=looks_like_false_table,
                normalize_text=normalize_text,
                contains_section_marker=OcrTableUtils.contains_section_marker,
                is_page_number_token=OcrTableUtils.is_page_number_token,
                dedupe_ocr_cells=OcrTableUtils.dedupe_ocr_cells,
                median_cell_height=OcrTableUtils.median_cell_height,
                cluster_ocr_rows=OcrTableUtils.cluster_ocr_rows,
                group_table_rows=group_table_rows,
                split_group_by_row_gaps=split_group_by_row_gaps,
                build_col_anchors=OcrTableUtils.build_col_anchors,
                nearest_anchor_index=OcrTableUtils.nearest_anchor_index,
                expand_group_with_sparse_rows=expand_group_with_sparse_rows,
                table_quality_score=table_quality_score,
                split_table_line=OcrTableUtils.split_table_line,
                is_table_line=OcrTableUtils.is_table_line,
                merge_same_page_tables=merge_same_page_tables,
                merge_cross_page_tables=merge_cross_page_tables,
            ),
        )
        figure_text_runtime = FigureTextRuntime(
            **parser_semantic_foundation_bundle_runtime.build_figure_text_kwargs(
                normalize_text=normalize_text,
                header_token_is_generic=TableHeaderRuntime.header_token_is_generic,
            )
        )
        table_pruning_runtime = TablePruningRuntime(
            **parser_semantic_foundation_bundle_runtime.build_table_pruning_kwargs(
                normalize_text=normalize_text,
                contains_section_marker=OcrTableUtils.contains_section_marker,
                header_token_is_generic=TableHeaderRuntime.header_token_is_generic,
            )
        )
        figure_inference = FigureInferenceRuntime(
            **parser_semantic_foundation_bundle_runtime.build_figure_inference_kwargs(
                vision_enable_figures=vision_enable_figures,
                normalize_text=normalize_text,
                normalize_token_for_compare=normalize_token_for_compare,
                contains_figure_marker=OcrTableUtils.contains_figure_marker,
                contains_catalog_marker=OcrTableUtils.contains_catalog_marker,
                strip_figure_caption_noise=figure_text_runtime.strip_figure_caption_noise,
                count_figure_markers_in_text=figure_text_runtime.count_figure_markers_in_text,
                next_figure_index=BlockIndexRuntime.next_figure_index,
            )
        )
        content_normalization_runtime = ContentNormalizationRuntime(
            **parser_semantic_foundation_bundle_runtime.build_content_normalization_kwargs(
                normalize_text=normalize_text,
            )
        )
        return {
            "_ocr_table_inference": ocr_table_inference,
            "_figure_text_runtime": figure_text_runtime,
            "_table_pruning_runtime": table_pruning_runtime,
            "_figure_inference": figure_inference,
            "_content_normalization_runtime": content_normalization_runtime,
        }
