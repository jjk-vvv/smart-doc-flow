from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .parser_config_runtime import ParserConfigRuntime
from .parser_docx_bootstrap_runtime import (
    ParserDispatchBundleRuntime,
    ParserDocxBootstrapRuntime,
    ParserDocxContentBundleRuntime,
    ParserDocxPdfEntryRuntime,
)
from .parser_document_table_bootstrap_runtime import ParserDocumentTableBootstrapRuntime
from .parser_image_bootstrap_runtime import ParserImageBootstrapRuntime, ParserImageBundleRuntime
from .parser_pdf_bootstrap_runtime import ParserPdfBootstrapRuntime, ParserPdfEntryRuntime
from .parser_semantic_bootstrap_runtime import (
    ParserOcrTableInferenceBundleRuntime,
    ParserSemanticBootstrapRuntime,
    ParserSemanticFoundationBundleRuntime,
)
from .parser_vision_transport_bootstrap_runtime import (
    ParserVisionBundleRuntime,
    ParserVisionTransportBootstrapRuntime,
)
from .parser_visual_context_bootstrap_runtime import (
    ParserVisualContextBootstrapRuntime,
    ParserVisualContextBundleRuntime,
)
from .parser_visual_execution_bootstrap_runtime import (
    ParserVisualExecutionBootstrapRuntime,
    ParserVisualExecutionBundleRuntime,
)
from .parser_visual_payload_bootstrap_runtime import (
    ParserVisualPayloadBootstrapRuntime,
    ParserVisualPayloadBundleRuntime,
)


ProviderFactory = Callable[..., Any]
KwargsBuilder = Callable[[], Dict[str, Any]]
TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
ParseResult = Tuple[str, Dict[str, List[float]], TableBlocks]
BuildNamedRuntimeStateFn = Callable[..., Dict[str, Any]]
BuildXlsxStateFn = Callable[..., Dict[str, Any]]
BuildPlainTextStateFn = Callable[..., Dict[str, Any]]
ApplyStateUpdateFn = Callable[[Dict[str, Any]], Optional[ParseResult]]
ParsePlainPayloadFn = Callable[..., Any]
MergeFigureBlocksFn = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]


@dataclass(frozen=True)
class ParserKwargBundle:
    config_kwargs: Dict[str, Any]
    callback_kwargs: Dict[str, Any]


class ParserProviderBundleRuntime:
    """Build pure provider kwargs for parser-owned lazy dependencies."""

    def build_mineru_layout_kwargs(
        self,
        *,
        backend: str,
        method: str,
        timeout_sec: int,
        cache_dir: str,
        enable_cache: bool,
        enable_formula: bool,
        enable_table: bool,
        device: str,
        method_fallbacks: str,
    ) -> Dict[str, Any]:
        return {
            "backend": backend,
            "method": method,
            "timeout_sec": timeout_sec,
            "cache_dir": cache_dir,
            "enable_cache": enable_cache,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "device": device,
            "method_fallbacks": method_fallbacks,
        }

    def build_roi_cropper_kwargs(
        self,
        *,
        table_dpi: int,
        figure_dpi: int,
        expand_ratio: float,
        max_side_px: int,
    ) -> Dict[str, Any]:
        return {
            "table_dpi": table_dpi,
            "figure_dpi": figure_dpi,
            "expand_ratio": expand_ratio,
            "max_side_px": max_side_px,
        }

    def build_visual_vision_kwargs(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        endpoint_style: str,
        timeout_sec: float,
        max_output_tokens: int,
        retry_count: int,
        cache_dir: str,
        enable_cache: bool,
        reasoning_effort: str,
    ) -> Dict[str, Any]:
        return {
            "api_key": api_key,
            "model": model,
            "base_url": base_url,
            "endpoint_style": endpoint_style,
            "timeout_sec": timeout_sec,
            "max_output_tokens": max_output_tokens,
            "retry_count": retry_count,
            "cache_dir": cache_dir,
            "enable_cache": enable_cache,
            "reasoning_effort": reasoning_effort,
        }


    def visual_backend_available(
        self,
        *,
        find_spec: Callable[[str], Any] | None = None,
    ) -> tuple[bool, str]:
        finder = find_spec if find_spec is not None else importlib.util.find_spec
        missing: list[str] = []
        try:
            fitz_available = finder("fitz") is not None
        except Exception:
            fitz_available = False
        if not fitz_available:
            missing.append("pymupdf")
        try:
            rapidocr_available = finder("rapidocr_onnxruntime") is not None
        except Exception:
            rapidocr_available = False
        if not rapidocr_available:
            missing.append("rapidocr-onnxruntime")
        if missing:
            return False, ", ".join(missing)
        return True, ""


class ParserProviderStateRuntime:
    """Manage lazily-created parser provider instances behind stable getters."""

    def __init__(
        self,
        *,
        mineru_layout_extractor_factory: ProviderFactory,
        build_mineru_layout_kwargs: KwargsBuilder,
        roi_cropper_factory: ProviderFactory,
        build_roi_cropper_kwargs: KwargsBuilder,
        visual_vision_extractor_factory: ProviderFactory,
        build_visual_vision_kwargs: KwargsBuilder,
    ) -> None:
        self._mineru_layout_extractor_factory = mineru_layout_extractor_factory
        self._build_mineru_layout_kwargs = build_mineru_layout_kwargs
        self._roi_cropper_factory = roi_cropper_factory
        self._build_roi_cropper_kwargs = build_roi_cropper_kwargs
        self._visual_vision_extractor_factory = visual_vision_extractor_factory
        self._build_visual_vision_kwargs = build_visual_vision_kwargs

        self._mineru_layout_extractor: Optional[Any] = None
        self._roi_cropper: Optional[Any] = None
        self._visual_vision_extractor: Optional[Any] = None

    def reset(self) -> None:
        self._mineru_layout_extractor = None
        self._roi_cropper = None
        self._visual_vision_extractor = None

    def get_mineru_layout_extractor(self) -> Any:
        if self._mineru_layout_extractor is None:
            self._mineru_layout_extractor = self._mineru_layout_extractor_factory(
                **self._build_mineru_layout_kwargs()
            )
        return self._mineru_layout_extractor

    def get_roi_cropper(self) -> Any:
        if self._roi_cropper is None:
            self._roi_cropper = self._roi_cropper_factory(**self._build_roi_cropper_kwargs())
        return self._roi_cropper

    def get_visual_vision_extractor(self) -> Any:
        if self._visual_vision_extractor is None:
            self._visual_vision_extractor = self._visual_vision_extractor_factory(
                **self._build_visual_vision_kwargs()
            )
        return self._visual_vision_extractor


class ParserDependencyBundleRuntime:
    """Build pure kwarg bundles for parser component runtimes."""

    def build_pdf_ocr_bundle(
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
        get_ocr_engine: Callable[..., Any],
        set_runtime_page_count: Callable[..., Any],
        normalize_text: Callable[..., Any],
        normalize_box: Callable[..., Any],
        build_ocr_page_indices: Callable[..., Any],
        looks_like_table_cue_text: Callable[..., Any],
        infer_tables_from_ocr_cells: Callable[..., Any],
        augment_with_line_tables: Callable[..., Any],
        need_line_table_augmentation: Callable[..., Any],
        select_line_augmentation_pages: Callable[..., Any],
        infer_tables_from_page_lines: Callable[..., Any],
        select_uncovered_table_like_pages: Callable[..., Any],
        infer_figures_from_page_lines: Callable[..., Any],
        get_last_figure_blocks: Callable[..., Any],
        enhance_low_quality_pages_with_vision: Callable[..., Any],
        merge_figure_blocks: Callable[..., Any],
        prune_fragment_tables: Callable[..., Any],
    ) -> ParserKwargBundle:
        return ParserKwargBundle(
            config_kwargs={
                "ocr_large_doc_dpi": ocr_large_doc_dpi,
                "ocr_large_doc_page_threshold": ocr_large_doc_page_threshold,
                "ocr_low_priority_dpi": ocr_low_priority_dpi,
                "ocr_high_priority_pages": ocr_high_priority_pages,
                "ocr_dense_cue_threshold": ocr_dense_cue_threshold,
                "ocr_max_attempt_pages_dense_cue": ocr_max_attempt_pages_dense_cue,
                "ocr_max_attempt_pages_mid_cue": ocr_max_attempt_pages_mid_cue,
                "ocr_dynamic_neighbor_pages": ocr_dynamic_neighbor_pages,
                "ocr_dynamic_neighbor_auto_enable": ocr_dynamic_neighbor_auto_enable,
                "ocr_dynamic_neighbor_auto_max": ocr_dynamic_neighbor_auto_max,
                "ocr_min_pages_before_budget": ocr_min_pages_before_budget,
                "ocr_front_scan_pages": ocr_front_scan_pages,
                "ocr_low_cue_boost_enable": ocr_low_cue_boost_enable,
                "ocr_low_cue_min_pages_cap": ocr_low_cue_min_pages_cap,
                "ocr_time_budget_max_sec": ocr_time_budget_max_sec,
                "ocr_time_budget_sec": ocr_time_budget_sec,
                "ocr_time_budget_per_page": ocr_time_budget_per_page,
                "ocr_budget_guard_ratio": ocr_budget_guard_ratio,
                "ocr_dynamic_early_stop_enable": ocr_dynamic_early_stop_enable,
                "ocr_dynamic_early_stop_min_pages": ocr_dynamic_early_stop_min_pages,
                "ocr_dynamic_early_stop_min_signal_pages": ocr_dynamic_early_stop_min_signal_pages,
                "ocr_dynamic_early_stop_streak": ocr_dynamic_early_stop_streak,
                "ocr_relaxed_trigger_table_count": ocr_relaxed_trigger_table_count,
                "ocr_table_relaxed_min_quality": ocr_table_relaxed_min_quality,
                "ocr_table_min_quality": ocr_table_min_quality,
                "ocr_uncovered_line_aug_pages": ocr_uncovered_line_aug_pages,
            },
            callback_kwargs={
                "get_ocr_engine": get_ocr_engine,
                "set_runtime_page_count": set_runtime_page_count,
                "normalize_text": normalize_text,
                "normalize_box": normalize_box,
                "build_ocr_page_indices": build_ocr_page_indices,
                "looks_like_table_cue_text": looks_like_table_cue_text,
                "infer_tables_from_ocr_cells": infer_tables_from_ocr_cells,
                "augment_with_line_tables": augment_with_line_tables,
                "need_line_table_augmentation": need_line_table_augmentation,
                "select_line_augmentation_pages": select_line_augmentation_pages,
                "infer_tables_from_page_lines": infer_tables_from_page_lines,
                "select_uncovered_table_like_pages": select_uncovered_table_like_pages,
                "infer_figures_from_page_lines": (
                    lambda page_lines, parts, bbox_map, source_prefix: infer_figures_from_page_lines(
                        page_lines,
                        parts,
                        bbox_map,
                        source_prefix,
                        get_last_figure_blocks(),
                    )
                ),
                "enhance_low_quality_pages_with_vision": enhance_low_quality_pages_with_vision,
                "merge_figure_blocks": merge_figure_blocks,
                "prune_fragment_tables": prune_fragment_tables,
            },
        )

    def build_pdf_native_bundle(
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
        vision_enable_figures: bool,
        normalize_text: Callable[..., Any],
        split_page_text: Callable[..., Any],
        append_ref: Callable[..., Any],
        collect_table_cue_pages: Callable[..., Any],
        extract_pdf_tables_with_fitz: Callable[..., Any],
        is_weak_native_table_result: Callable[..., Any],
        select_line_augmentation_pages: Callable[..., Any],
        infer_tables_from_page_lines: Callable[..., Any],
        augment_with_line_tables: Callable[..., Any],
        merge_same_page_tables: Callable[..., Any],
        merge_cross_page_tables: Callable[..., Any],
        infer_figures_from_page_lines: Callable[..., Any],
        figure_blocks_need_vision: Callable[..., Any],
        enhance_low_quality_pages_with_vision: Callable[..., Any],
        merge_figure_blocks: Callable[..., Any],
        prune_fragment_tables: Callable[..., Any],
    ) -> ParserKwargBundle:
        return ParserKwargBundle(
            config_kwargs={
                "max_pages": max_pages,
                "max_pages_visual": max_pages_visual,
                "visual_probe_pages": visual_probe_pages,
                "native_text_threshold": native_text_threshold,
                "ocr_cue_scan_pages": ocr_cue_scan_pages,
                "enable_fitz_table": enable_fitz_table,
                "table_merge_enable": table_merge_enable,
                "visual_force_ocr_on_weak_native": visual_force_ocr_on_weak_native,
                "vision_enable_figures": vision_enable_figures,
            },
            callback_kwargs={
                "normalize_text": normalize_text,
                "split_page_text": split_page_text,
                "append_ref": append_ref,
                "collect_table_cue_pages": collect_table_cue_pages,
                "extract_pdf_tables_with_fitz": extract_pdf_tables_with_fitz,
                "is_weak_native_table_result": is_weak_native_table_result,
                "select_line_augmentation_pages": select_line_augmentation_pages,
                "infer_tables_from_page_lines": infer_tables_from_page_lines,
                "augment_with_line_tables": augment_with_line_tables,
                "merge_same_page_tables": merge_same_page_tables,
                "merge_cross_page_tables": merge_cross_page_tables,
                "infer_figures_from_page_lines": infer_figures_from_page_lines,
                "figure_blocks_need_vision": figure_blocks_need_vision,
                "enhance_low_quality_pages_with_vision": enhance_low_quality_pages_with_vision,
                "merge_figure_blocks": merge_figure_blocks,
                "prune_fragment_tables": prune_fragment_tables,
            },
        )

    def build_docx_enrichment_bundle(
        self,
        *,
        artifact_root_dir: Any,
        image_extensions: set[str],
        docx_chart_xml_enable: bool,
        docx_media_probe_enable: bool,
        docx_media_max_assets: int,
        docx_media_vision_enable: bool,
        docx_media_nested_vision_enhance_enable: bool,
        docx_media_max_assets_unbounded: bool,
        docx_media_vision_max_assets: int,
        docx_media_vision_max_assets_unbounded: bool,
        docx_media_vision_max_bytes: int,
        docx_media_vision_chart_only: bool,
        docx_media_vision_allow_noncue: bool,
        nonpdf_figure_max: int,
        normalize_text: Callable[..., Any],
        safe_text_list: Callable[..., Any],
        looks_like_figure_cue_text: Callable[..., Any],
        normalize_dataframe_headers: Callable[..., Any],
        normalize_dataframe_matrix: Callable[..., Any],
        decorate_rows_with_meta: Callable[..., Any],
        build_header_meta: Callable[..., Any],
        parse_image: Callable[..., Any],
        get_last_figure_blocks: Callable[..., Any],
        set_last_figure_blocks: Callable[..., Any],
    ) -> ParserKwargBundle:
        return ParserKwargBundle(
            config_kwargs={
                "artifact_root_dir": artifact_root_dir,
                "image_extensions": set(image_extensions or set()),
                "docx_chart_xml_enable": docx_chart_xml_enable,
                "docx_media_probe_enable": docx_media_probe_enable,
                "docx_media_max_assets": docx_media_max_assets,
                "docx_media_vision_enable": docx_media_vision_enable,
                "docx_media_nested_vision_enhance_enable": docx_media_nested_vision_enhance_enable,
                "docx_media_max_assets_unbounded": docx_media_max_assets_unbounded,
                "docx_media_vision_max_assets": docx_media_vision_max_assets,
                "docx_media_vision_max_assets_unbounded": docx_media_vision_max_assets_unbounded,
                "docx_media_vision_max_bytes": docx_media_vision_max_bytes,
                "docx_media_vision_chart_only": docx_media_vision_chart_only,
                "docx_media_vision_allow_noncue": docx_media_vision_allow_noncue,
                "nonpdf_figure_max": nonpdf_figure_max,
            },
            callback_kwargs={
                "normalize_text": normalize_text,
                "safe_text_list": safe_text_list,
                "looks_like_figure_cue_text": looks_like_figure_cue_text,
                "normalize_dataframe_headers": normalize_dataframe_headers,
                "normalize_dataframe_matrix": normalize_dataframe_matrix,
                "decorate_rows_with_meta": decorate_rows_with_meta,
                "build_header_meta": build_header_meta,
                "parse_image": parse_image,
                "get_last_figure_blocks": get_last_figure_blocks,
                "set_last_figure_blocks": set_last_figure_blocks,
            },
        )


class ParserNonPdfEntryRuntime:
    """Coordinate parser-owned non-PDF entry adapters without keeping them inline in parser.py."""

    def parse_docx(
        self,
        *,
        docx_document_runtime: Any,
        file_bytes: bytes,
        build_named_runtime_state: BuildNamedRuntimeStateFn,
        apply_state_update: ApplyStateUpdateFn,
    ) -> ParseResult:
        runtime_result = docx_document_runtime.parse_docx(file_bytes)
        result = apply_state_update(build_named_runtime_state(runtime_result))
        if result is None:
            raise ValueError("DOCX parse state update returned no result.")
        return result

    def parse_docx_relaxed(
        self,
        *,
        docx_document_runtime: Any,
        file_bytes: bytes,
        build_named_runtime_state: BuildNamedRuntimeStateFn,
        apply_state_update: ApplyStateUpdateFn,
    ) -> ParseResult:
        runtime_result = docx_document_runtime.parse_docx_relaxed(file_bytes)
        result = apply_state_update(build_named_runtime_state(runtime_result))
        if result is None:
            raise ValueError("Relaxed DOCX parse state update returned no result.")
        return result

    def parse_xlsx(
        self,
        *,
        xlsx_parse_runtime: Any,
        file_bytes: bytes,
        build_xlsx_state: BuildXlsxStateFn,
        apply_state_update: ApplyStateUpdateFn,
    ) -> ParseResult:
        markdown, bbox_map, table_blocks, used_zip_fallback = xlsx_parse_runtime.parse_xlsx(
            file_bytes=file_bytes,
        )
        result = apply_state_update(
            build_xlsx_state(
                markdown=markdown,
                bbox_map=bbox_map,
                table_blocks=table_blocks,
                used_zip_fallback=used_zip_fallback,
            )
        )
        if result is None:
            raise ValueError("XLSX parse state update returned no result.")
        return result

    def parse_image(
        self,
        *,
        image_document_runtime: Any,
        file_name: str,
        file_bytes: bytes,
        last_figure_blocks: FigureBlocks,
        build_named_runtime_state: BuildNamedRuntimeStateFn,
        apply_state_update: ApplyStateUpdateFn,
        enable_vision_enhance: bool | None = None,
    ) -> ParseResult:
        runtime_result = image_document_runtime.parse_image(
            file_name=file_name,
            file_bytes=file_bytes,
            last_figure_blocks=last_figure_blocks,
            enable_vision_enhance=enable_vision_enhance,
        )
        result = apply_state_update(
            build_named_runtime_state(
                runtime_result,
                include_stats=False,
            )
        )
        if result is None:
            raise ValueError("Image parse state update returned no result.")
        return result

    def parse_plain(
        self,
        *,
        file_bytes: bytes,
        ext: str,
        table_max_rows: int,
        table_max_cols: int,
        nonpdf_figure_max: int,
        parse_plain_payload: ParsePlainPayloadFn,
        build_header_meta: Any,
        decorate_rows_with_meta: Any,
        looks_like_figure_cue_text: Any,
        merge_figure_blocks: MergeFigureBlocksFn,
        build_plain_text_state: BuildPlainTextStateFn,
        apply_state_update: ApplyStateUpdateFn,
    ) -> ParseResult:
        plain_result = parse_plain_payload(
            file_bytes,
            ext,
            table_max_rows=table_max_rows,
            table_max_cols=table_max_cols,
            nonpdf_figure_max=nonpdf_figure_max,
            build_header_meta=build_header_meta,
            decorate_rows_with_meta=decorate_rows_with_meta,
            looks_like_figure_cue_text=looks_like_figure_cue_text,
        )
        result = apply_state_update(
            build_plain_text_state(
                ext=ext,
                plain_result=plain_result,
                merged_figure_blocks=merge_figure_blocks([], getattr(plain_result, "figure_blocks", []) or []),
            )
        )
        if result is None:
            raise ValueError("Plain text parse state update returned no result.")
        return result


class ParserBootstrapRuntime:
    """Build parser bootstrap/runtime wiring objects without leaving the setup inline in parser.py."""

    def build_support_runtime_attrs(
        self,
        *,
        getenv: Callable[[str, str | None], str | None],
        limit_env_value: Callable[..., Any],
        module2_root: Path,
        repo_root: Path,
    ) -> Dict[str, Any]:
        return {
            "_parser_config_runtime": ParserConfigRuntime(
                getenv=getenv,
                limit_env_value=limit_env_value,
                module2_root=module2_root,
                repo_root=repo_root,
            ),
            "_parser_ocr_table_inference_bundle_runtime": ParserOcrTableInferenceBundleRuntime(),
            "_parser_provider_bundle_runtime": ParserProviderBundleRuntime(),
            "_parser_image_bundle_runtime": ParserImageBundleRuntime(),
            "_parser_image_bootstrap_runtime": ParserImageBootstrapRuntime(),
            "_parser_dispatch_bundle_runtime": ParserDispatchBundleRuntime(),
            "_parser_docx_bootstrap_runtime": ParserDocxBootstrapRuntime(),
            "_parser_docx_content_bundle_runtime": ParserDocxContentBundleRuntime(),
            "_parser_document_table_bootstrap_runtime": ParserDocumentTableBootstrapRuntime(),
            "_parser_docx_pdf_entry_runtime": ParserDocxPdfEntryRuntime(),
            "_parser_nonpdf_entry_runtime": ParserNonPdfEntryRuntime(),
            "_parser_pdf_bootstrap_runtime": ParserPdfBootstrapRuntime(),
            "_parser_pdf_entry_runtime": ParserPdfEntryRuntime(),
            "_parser_vision_bundle_runtime": ParserVisionBundleRuntime(),
            "_parser_vision_transport_bootstrap_runtime": ParserVisionTransportBootstrapRuntime(),
            "_parser_visual_payload_bootstrap_runtime": ParserVisualPayloadBootstrapRuntime(),
            "_parser_visual_payload_bundle_runtime": ParserVisualPayloadBundleRuntime(),
            "_parser_visual_context_bootstrap_runtime": ParserVisualContextBootstrapRuntime(),
            "_parser_visual_context_bundle_runtime": ParserVisualContextBundleRuntime(),
            "_parser_visual_execution_bootstrap_runtime": ParserVisualExecutionBootstrapRuntime(),
            "_parser_visual_execution_bundle_runtime": ParserVisualExecutionBundleRuntime(),
            "_parser_semantic_bootstrap_runtime": ParserSemanticBootstrapRuntime(),
            "_parser_semantic_foundation_bundle_runtime": ParserSemanticFoundationBundleRuntime(),
        }

    def build_provider_state_runtime(
        self,
        *,
        mineru_layout_extractor_factory: Callable[..., Any],
        build_mineru_layout_kwargs: Callable[[], Dict[str, Any]],
        roi_cropper_factory: Callable[..., Any],
        build_roi_cropper_kwargs: Callable[[], Dict[str, Any]],
        visual_vision_extractor_factory: Callable[..., Any],
        build_visual_vision_kwargs: Callable[[], Dict[str, Any]],
    ) -> ParserProviderStateRuntime:
        return ParserProviderStateRuntime(
            mineru_layout_extractor_factory=mineru_layout_extractor_factory,
            build_mineru_layout_kwargs=build_mineru_layout_kwargs,
            roi_cropper_factory=roi_cropper_factory,
            build_roi_cropper_kwargs=build_roi_cropper_kwargs,
            visual_vision_extractor_factory=visual_vision_extractor_factory,
            build_visual_vision_kwargs=build_visual_vision_kwargs,
        )
