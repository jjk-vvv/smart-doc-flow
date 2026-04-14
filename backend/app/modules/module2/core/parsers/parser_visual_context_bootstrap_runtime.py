from __future__ import annotations

from typing import Any, Callable, Dict

from ..table.ocr_table_utils import OcrTableUtils
from ..pdf.pdf_visual_profile import PdfVisualProfileRuntime
from ..schema.reference_runtime import ReferenceRuntime
from ..visual.visual_planning_runtime import VisualLayoutSelectorRuntime, VisualObjectContextRuntime
from ..visual.visual_pdf_bootstrap import (
    VisualPdfBootstrapRuntime,
    VisualPdfPrepareRuntime,
    VisualRuntimeLimitsRuntime,
)
from ..visual.visual_parse_orchestrator import VisualStatusBuilderRuntime


RuntimeCallback = Callable[..., Any]


class ParserVisualContextBundleRuntime:
    """Build pure kwargs for parser-owned visual profile/context runtimes."""

    def build_pdf_visual_profile_kwargs(
        self,
        *,
        native_text_threshold: int,
        visual_probe_pages: int,
        mineru_method: str,
        mineru_scanned_method: str,
        mineru_method_fallbacks: str,
        visual_first_max_pages_scanned: int,
        mineru_text_first_office_pdf_enable: bool,
        mineru_text_first_office_pdf_min_pages: int,
        mineru_text_first_office_pdf_min_probe_chars: int,
        pdf_text_first_enable: bool,
        pdf_text_heavy_min_probe_chars: int,
        pdf_text_heavy_min_chars_per_page: int,
        pdf_text_heavy_max_visual_cues: int,
        pdf_mixed_text_pref_min_chars_per_page: int,
        pdf_mixed_text_pref_max_visual_cues: int,
        pdf_text_only_short_circuit_enable: bool,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "native_text_threshold": native_text_threshold,
            "visual_probe_pages": visual_probe_pages,
            "mineru_method": mineru_method,
            "mineru_scanned_method": mineru_scanned_method,
            "mineru_method_fallbacks": mineru_method_fallbacks,
            "visual_first_max_pages_scanned": visual_first_max_pages_scanned,
            "mineru_text_first_office_pdf_enable": mineru_text_first_office_pdf_enable,
            "mineru_text_first_office_pdf_min_pages": mineru_text_first_office_pdf_min_pages,
            "mineru_text_first_office_pdf_min_probe_chars": mineru_text_first_office_pdf_min_probe_chars,
            "pdf_text_first_enable": pdf_text_first_enable,
            "pdf_text_heavy_min_probe_chars": pdf_text_heavy_min_probe_chars,
            "pdf_text_heavy_min_chars_per_page": pdf_text_heavy_min_chars_per_page,
            "pdf_text_heavy_max_visual_cues": pdf_text_heavy_max_visual_cues,
            "pdf_mixed_text_pref_min_chars_per_page": pdf_mixed_text_pref_min_chars_per_page,
            "pdf_mixed_text_pref_max_visual_cues": pdf_mixed_text_pref_max_visual_cues,
            "pdf_text_only_short_circuit_enable": pdf_text_only_short_circuit_enable,
            "normalize_text": normalize_text,
        }

    def build_visual_runtime_limits_kwargs(
        self,
        *,
        image_extensions: set[str],
        visual_max_objects: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_chart_score_min: int,
        visual_figure_cueless_fallback_max: int,
        visual_figure_refine_budget: int,
        visual_figure_refine_min_score: int,
        visual_runtime_large_doc_page_threshold: int,
        visual_runtime_large_doc_image_threshold: int,
        visual_runtime_large_doc_max_objects: int,
        visual_runtime_large_doc_figure_max_per_page: int,
        visual_runtime_large_doc_cueless_fallback_max: int,
        visual_runtime_large_doc_chart_score_min: int,
        visual_runtime_large_doc_refine_budget: int,
        visual_runtime_extreme_doc_page_threshold: int,
        visual_runtime_extreme_doc_max_objects: int,
        visual_runtime_extreme_doc_figure_max_per_page: int,
        visual_runtime_extreme_doc_cueless_fallback_max: int,
        visual_runtime_extreme_doc_chart_score_min: int,
        visual_runtime_extreme_doc_refine_budget: int,
    ) -> Dict[str, Any]:
        return {
            "image_extensions": image_extensions,
            "visual_max_objects": visual_max_objects,
            "visual_table_max_per_page": visual_table_max_per_page,
            "visual_figure_max_per_page": visual_figure_max_per_page,
            "visual_figure_chart_score_min": visual_figure_chart_score_min,
            "visual_figure_cueless_fallback_max": visual_figure_cueless_fallback_max,
            "visual_figure_refine_budget": visual_figure_refine_budget,
            "visual_figure_refine_min_score": visual_figure_refine_min_score,
            "visual_runtime_large_doc_page_threshold": visual_runtime_large_doc_page_threshold,
            "visual_runtime_large_doc_image_threshold": visual_runtime_large_doc_image_threshold,
            "visual_runtime_large_doc_max_objects": visual_runtime_large_doc_max_objects,
            "visual_runtime_large_doc_figure_max_per_page": visual_runtime_large_doc_figure_max_per_page,
            "visual_runtime_large_doc_cueless_fallback_max": visual_runtime_large_doc_cueless_fallback_max,
            "visual_runtime_large_doc_chart_score_min": visual_runtime_large_doc_chart_score_min,
            "visual_runtime_large_doc_refine_budget": visual_runtime_large_doc_refine_budget,
            "visual_runtime_extreme_doc_page_threshold": visual_runtime_extreme_doc_page_threshold,
            "visual_runtime_extreme_doc_max_objects": visual_runtime_extreme_doc_max_objects,
            "visual_runtime_extreme_doc_figure_max_per_page": visual_runtime_extreme_doc_figure_max_per_page,
            "visual_runtime_extreme_doc_cueless_fallback_max": visual_runtime_extreme_doc_cueless_fallback_max,
            "visual_runtime_extreme_doc_chart_score_min": visual_runtime_extreme_doc_chart_score_min,
            "visual_runtime_extreme_doc_refine_budget": visual_runtime_extreme_doc_refine_budget,
        }

    def build_visual_pdf_bootstrap_kwargs(
        self,
        *,
        visual_probe_pages: int,
        visual_first_max_pages: int,
        max_pages: int,
        mineru_method: str,
        visual_runtime_extreme_doc_page_threshold: int,
        visual_runtime_office_text_layout_page_cap: int,
        visual_runtime_mixed_text_layout_page_cap: int,
        visual_runtime_extreme_doc_layout_page_cap: int,
        normalize_text: RuntimeCallback,
        summarize_pdf_metadata_signals: RuntimeCallback,
        classify_pdf_visual_profile: RuntimeCallback,
        resolve_visual_runtime_limits: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "visual_probe_pages": visual_probe_pages,
            "visual_first_max_pages": visual_first_max_pages,
            "max_pages": max_pages,
            "mineru_method": mineru_method,
            "visual_runtime_extreme_doc_page_threshold": visual_runtime_extreme_doc_page_threshold,
            "visual_runtime_office_text_layout_page_cap": visual_runtime_office_text_layout_page_cap,
            "visual_runtime_mixed_text_layout_page_cap": visual_runtime_mixed_text_layout_page_cap,
            "visual_runtime_extreme_doc_layout_page_cap": visual_runtime_extreme_doc_layout_page_cap,
            "normalize_text": normalize_text,
            "summarize_pdf_metadata_signals": summarize_pdf_metadata_signals,
            "classify_pdf_visual_profile": classify_pdf_visual_profile,
            "resolve_visual_runtime_limits": resolve_visual_runtime_limits,
        }

    def build_visual_pdf_prepare_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        split_page_text: RuntimeCallback,
        append_ref: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "split_page_text": split_page_text,
            "append_ref": append_ref,
        }

    def build_visual_object_context_kwargs(
        self,
        *,
        visual_context_max_chars: int,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "visual_context_max_chars": visual_context_max_chars,
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
        }

    def build_visual_layout_selector_kwargs(
        self,
        *,
        visual_max_objects: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_chart_score_min: int,
        visual_figure_cueless_fallback_max: int,
        visual_figure_chart_only: bool,
        visual_figure_allow_cueless_fallback: bool,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        infer_figure_type_from_text: RuntimeCallback,
        contains_table_marker: RuntimeCallback,
        contains_figure_marker: RuntimeCallback,
        looks_like_figure_cue_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "visual_max_objects": visual_max_objects,
            "visual_table_max_per_page": visual_table_max_per_page,
            "visual_figure_max_per_page": visual_figure_max_per_page,
            "visual_figure_chart_score_min": visual_figure_chart_score_min,
            "visual_figure_cueless_fallback_max": visual_figure_cueless_fallback_max,
            "visual_figure_chart_only": visual_figure_chart_only,
            "visual_figure_allow_cueless_fallback": visual_figure_allow_cueless_fallback,
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
            "infer_figure_type_from_text": infer_figure_type_from_text,
            "contains_table_marker": contains_table_marker,
            "contains_figure_marker": contains_figure_marker,
            "looks_like_figure_cue_text": looks_like_figure_cue_text,
        }


class ParserVisualContextBootstrapRuntime:
    """Build visual profile/context runtimes so parser.py keeps only stage orchestration."""

    def build_visual_context_runtime_attrs(
        self,
        *,
        parser_visual_context_bundle_runtime: Any,
        image_extensions: set[str],
        native_text_threshold: int,
        visual_probe_pages: int,
        mineru_method: str,
        mineru_scanned_method: str,
        mineru_method_fallbacks: str,
        visual_first_max_pages_scanned: int,
        mineru_text_first_office_pdf_enable: bool,
        mineru_text_first_office_pdf_min_pages: int,
        mineru_text_first_office_pdf_min_probe_chars: int,
        pdf_text_first_enable: bool,
        pdf_text_heavy_min_probe_chars: int,
        pdf_text_heavy_min_chars_per_page: int,
        pdf_text_heavy_max_visual_cues: int,
        pdf_mixed_text_pref_min_chars_per_page: int,
        pdf_mixed_text_pref_max_visual_cues: int,
        pdf_text_only_short_circuit_enable: bool,
        visual_max_objects: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_chart_score_min: int,
        visual_figure_cueless_fallback_max: int,
        visual_figure_refine_budget: int,
        visual_figure_refine_min_score: int,
        visual_runtime_large_doc_page_threshold: int,
        visual_runtime_large_doc_image_threshold: int,
        visual_runtime_large_doc_max_objects: int,
        visual_runtime_large_doc_figure_max_per_page: int,
        visual_runtime_large_doc_cueless_fallback_max: int,
        visual_runtime_large_doc_chart_score_min: int,
        visual_runtime_large_doc_refine_budget: int,
        visual_runtime_extreme_doc_page_threshold: int,
        visual_runtime_extreme_doc_max_objects: int,
        visual_runtime_extreme_doc_figure_max_per_page: int,
        visual_runtime_extreme_doc_cueless_fallback_max: int,
        visual_runtime_extreme_doc_chart_score_min: int,
        visual_runtime_extreme_doc_refine_budget: int,
        visual_first_max_pages: int,
        max_pages: int,
        visual_runtime_office_text_layout_page_cap: int,
        visual_runtime_mixed_text_layout_page_cap: int,
        visual_runtime_extreme_doc_layout_page_cap: int,
        visual_context_max_chars: int,
        visual_figure_chart_only: bool,
        visual_figure_allow_cueless_fallback: bool,
        normalize_text: RuntimeCallback,
        split_page_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        infer_figure_type_from_text: RuntimeCallback,
        looks_like_figure_cue_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        pdf_visual_profile_runtime = PdfVisualProfileRuntime(
            **parser_visual_context_bundle_runtime.build_pdf_visual_profile_kwargs(
                native_text_threshold=native_text_threshold,
                visual_probe_pages=visual_probe_pages,
                mineru_method=mineru_method,
                mineru_scanned_method=mineru_scanned_method,
                mineru_method_fallbacks=mineru_method_fallbacks,
                visual_first_max_pages_scanned=visual_first_max_pages_scanned,
                mineru_text_first_office_pdf_enable=mineru_text_first_office_pdf_enable,
                mineru_text_first_office_pdf_min_pages=mineru_text_first_office_pdf_min_pages,
                mineru_text_first_office_pdf_min_probe_chars=mineru_text_first_office_pdf_min_probe_chars,
                pdf_text_first_enable=pdf_text_first_enable,
                pdf_text_heavy_min_probe_chars=pdf_text_heavy_min_probe_chars,
                pdf_text_heavy_min_chars_per_page=pdf_text_heavy_min_chars_per_page,
                pdf_text_heavy_max_visual_cues=pdf_text_heavy_max_visual_cues,
                pdf_mixed_text_pref_min_chars_per_page=pdf_mixed_text_pref_min_chars_per_page,
                pdf_mixed_text_pref_max_visual_cues=pdf_mixed_text_pref_max_visual_cues,
                pdf_text_only_short_circuit_enable=pdf_text_only_short_circuit_enable,
                normalize_text=normalize_text,
            )
        )
        visual_runtime_limits_runtime = VisualRuntimeLimitsRuntime(
            **parser_visual_context_bundle_runtime.build_visual_runtime_limits_kwargs(
                image_extensions=image_extensions,
                visual_max_objects=visual_max_objects,
                visual_table_max_per_page=visual_table_max_per_page,
                visual_figure_max_per_page=visual_figure_max_per_page,
                visual_figure_chart_score_min=visual_figure_chart_score_min,
                visual_figure_cueless_fallback_max=visual_figure_cueless_fallback_max,
                visual_figure_refine_budget=visual_figure_refine_budget,
                visual_figure_refine_min_score=visual_figure_refine_min_score,
                visual_runtime_large_doc_page_threshold=visual_runtime_large_doc_page_threshold,
                visual_runtime_large_doc_image_threshold=visual_runtime_large_doc_image_threshold,
                visual_runtime_large_doc_max_objects=visual_runtime_large_doc_max_objects,
                visual_runtime_large_doc_figure_max_per_page=visual_runtime_large_doc_figure_max_per_page,
                visual_runtime_large_doc_cueless_fallback_max=visual_runtime_large_doc_cueless_fallback_max,
                visual_runtime_large_doc_chart_score_min=visual_runtime_large_doc_chart_score_min,
                visual_runtime_large_doc_refine_budget=visual_runtime_large_doc_refine_budget,
                visual_runtime_extreme_doc_page_threshold=visual_runtime_extreme_doc_page_threshold,
                visual_runtime_extreme_doc_max_objects=visual_runtime_extreme_doc_max_objects,
                visual_runtime_extreme_doc_figure_max_per_page=visual_runtime_extreme_doc_figure_max_per_page,
                visual_runtime_extreme_doc_cueless_fallback_max=visual_runtime_extreme_doc_cueless_fallback_max,
                visual_runtime_extreme_doc_chart_score_min=visual_runtime_extreme_doc_chart_score_min,
                visual_runtime_extreme_doc_refine_budget=visual_runtime_extreme_doc_refine_budget,
            )
        )
        visual_status_builder_runtime = VisualStatusBuilderRuntime()
        visual_pdf_bootstrap_runtime = VisualPdfBootstrapRuntime(
            **parser_visual_context_bundle_runtime.build_visual_pdf_bootstrap_kwargs(
                visual_probe_pages=visual_probe_pages,
                visual_first_max_pages=visual_first_max_pages,
                max_pages=max_pages,
                mineru_method=mineru_method,
                visual_runtime_extreme_doc_page_threshold=visual_runtime_extreme_doc_page_threshold,
                visual_runtime_office_text_layout_page_cap=visual_runtime_office_text_layout_page_cap,
                visual_runtime_mixed_text_layout_page_cap=visual_runtime_mixed_text_layout_page_cap,
                visual_runtime_extreme_doc_layout_page_cap=visual_runtime_extreme_doc_layout_page_cap,
                normalize_text=normalize_text,
                summarize_pdf_metadata_signals=pdf_visual_profile_runtime.summarize_pdf_metadata_signals,
                classify_pdf_visual_profile=pdf_visual_profile_runtime.classify_pdf_visual_profile,
                resolve_visual_runtime_limits=visual_runtime_limits_runtime.resolve_visual_runtime_limits,
            )
        )
        visual_pdf_prepare_runtime = VisualPdfPrepareRuntime(
            **parser_visual_context_bundle_runtime.build_visual_pdf_prepare_kwargs(
                normalize_text=normalize_text,
                split_page_text=split_page_text,
                append_ref=ReferenceRuntime.append_ref,
            )
        )
        visual_object_context_runtime = VisualObjectContextRuntime(
            **parser_visual_context_bundle_runtime.build_visual_object_context_kwargs(
                visual_context_max_chars=visual_context_max_chars,
                normalize_text=normalize_text,
                safe_text_list=safe_text_list,
            )
        )
        visual_layout_selector_runtime = VisualLayoutSelectorRuntime(
            **parser_visual_context_bundle_runtime.build_visual_layout_selector_kwargs(
                visual_max_objects=visual_max_objects,
                visual_table_max_per_page=visual_table_max_per_page,
                visual_figure_max_per_page=visual_figure_max_per_page,
                visual_figure_chart_score_min=visual_figure_chart_score_min,
                visual_figure_cueless_fallback_max=visual_figure_cueless_fallback_max,
                visual_figure_chart_only=visual_figure_chart_only,
                visual_figure_allow_cueless_fallback=visual_figure_allow_cueless_fallback,
                normalize_text=normalize_text,
                safe_text_list=safe_text_list,
                infer_figure_type_from_text=infer_figure_type_from_text,
                contains_table_marker=OcrTableUtils.contains_table_marker,
                contains_figure_marker=OcrTableUtils.contains_figure_marker,
                looks_like_figure_cue_text=looks_like_figure_cue_text,
            )
        )
        return {
            "_pdf_visual_profile_runtime": pdf_visual_profile_runtime,
            "_visual_runtime_limits_runtime": visual_runtime_limits_runtime,
            "_visual_status_builder_runtime": visual_status_builder_runtime,
            "_visual_pdf_bootstrap_runtime": visual_pdf_bootstrap_runtime,
            "_visual_pdf_prepare_runtime": visual_pdf_prepare_runtime,
            "_visual_object_context_runtime": visual_object_context_runtime,
            "_visual_layout_selector_runtime": visual_layout_selector_runtime,
        }
