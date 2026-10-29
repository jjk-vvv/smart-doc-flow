from __future__ import annotations

from typing import Any, Callable, Dict

from ..pipeline.block_index_runtime import BlockIndexRuntime
from ..format.image_document_runtime import ImageDocumentRuntime, ImageOcrRuntime, ImageParseRuntime, ImageVisionRuntime
from ..schema.reference_runtime import ReferenceRuntime
from ..visual.visual_payload_builder import VisualBboxRuntime


RuntimeCallback = Callable[..., Any]


class ParserImageBundleRuntime:
    """Build pure kwargs for parser-owned image parsing runtimes."""

    def build_image_ocr_kwargs(
        self,
        *,
        max_pages_visual: int,
        set_runtime_page_count: RuntimeCallback,
        append_ref: RuntimeCallback,
        normalize_text: RuntimeCallback,
        normalize_box: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "max_pages_visual": max_pages_visual,
            "set_runtime_page_count": set_runtime_page_count,
            "append_ref": append_ref,
            "normalize_text": normalize_text,
            "normalize_box": normalize_box,
        }

    def build_image_vision_kwargs(
        self,
        *,
        enabled: bool,
        vision_max_pages: int,
        vision_consecutive_fail_stop: int,
        resolve_api_key: RuntimeCallback,
        select_low_quality_pages_for_vision: RuntimeCallback,
        vision_focus_from_page_lines: RuntimeCallback,
        render_page_png_for_vision: RuntimeCallback,
        extract_payload: RuntimeCallback,
        extract_vision_insights: RuntimeCallback,
        append_ref: RuntimeCallback,
        build_tables_from_vision_payload: RuntimeCallback,
        build_figures_from_vision_payload: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        augment_with_line_tables: RuntimeCallback,
        next_table_index: RuntimeCallback,
        next_figure_index: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "enabled": enabled,
            "vision_max_pages": vision_max_pages,
            "vision_consecutive_fail_stop": vision_consecutive_fail_stop,
            "resolve_api_key": resolve_api_key,
            "select_low_quality_pages_for_vision": select_low_quality_pages_for_vision,
            "vision_focus_from_page_lines": vision_focus_from_page_lines,
            "render_page_png_for_vision": render_page_png_for_vision,
            "extract_payload": extract_payload,
            "extract_vision_insights": extract_vision_insights,
            "append_ref": append_ref,
            "build_tables_from_vision_payload": build_tables_from_vision_payload,
            "build_figures_from_vision_payload": build_figures_from_vision_payload,
            "merge_figure_blocks": merge_figure_blocks,
            "augment_with_line_tables": augment_with_line_tables,
            "next_table_index": next_table_index,
            "next_figure_index": next_figure_index,
        }

    def build_image_parse_kwargs(
        self,
        *,
        infer_tables_from_ocr_cells: RuntimeCallback,
        infer_tables_from_page_lines: RuntimeCallback,
        infer_figures_from_page_lines: RuntimeCallback,
        enhance_low_quality_pages_with_vision: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        prune_fragment_tables: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "infer_tables_from_ocr_cells": infer_tables_from_ocr_cells,
            "infer_tables_from_page_lines": infer_tables_from_page_lines,
            "infer_figures_from_page_lines": infer_figures_from_page_lines,
            "enhance_low_quality_pages_with_vision": enhance_low_quality_pages_with_vision,
            "merge_figure_blocks": merge_figure_blocks,
            "prune_fragment_tables": prune_fragment_tables,
        }

    def build_image_document_kwargs(
        self,
        *,
        vision_enhance_enabled: bool,
        visual_backend_available: RuntimeCallback,
        resolve_api_key: RuntimeCallback,
        get_ocr_engine: RuntimeCallback,
        collect_page_ocr: RuntimeCallback,
        build_parse_result: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_enhance_enabled": vision_enhance_enabled,
            "visual_backend_available": visual_backend_available,
            "resolve_api_key": resolve_api_key,
            "get_ocr_engine": get_ocr_engine,
            "collect_page_ocr": collect_page_ocr,
            "build_parse_result": build_parse_result,
        }


class ParserImageBootstrapRuntime:
    """Build image parsing runtimes so parser.py only coordinates bootstrap order."""

    def build_image_runtime_attrs(
        self,
        *,
        parser_image_bundle_runtime: Any,
        max_pages_visual: int,
        vision_enhance_enabled: bool,
        vision_max_pages: int,
        vision_consecutive_fail_stop: int,
        set_runtime_page_count: RuntimeCallback,
        visual_backend_available: RuntimeCallback,
        resolve_api_key: RuntimeCallback,
        get_ocr_engine: RuntimeCallback,
        normalize_text: RuntimeCallback,
        select_low_quality_pages_for_vision: RuntimeCallback,
        vision_focus_from_page_lines: RuntimeCallback,
        render_page_png_for_vision: RuntimeCallback,
        extract_payload: RuntimeCallback,
        extract_vision_insights: RuntimeCallback,
        build_tables_from_vision_payload: RuntimeCallback,
        build_figures_from_vision_payload: RuntimeCallback,
        infer_tables_from_ocr_cells: RuntimeCallback,
        infer_tables_from_page_lines: RuntimeCallback,
        infer_figures_from_page_lines: RuntimeCallback,
        enhance_low_quality_pages_with_vision: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        augment_with_line_tables: RuntimeCallback,
        prune_fragment_tables: RuntimeCallback,
    ) -> Dict[str, Any]:
        image_ocr_runtime = ImageOcrRuntime(
            **parser_image_bundle_runtime.build_image_ocr_kwargs(
                max_pages_visual=max_pages_visual,
                set_runtime_page_count=set_runtime_page_count,
                append_ref=ReferenceRuntime.append_ref,
                normalize_text=normalize_text,
                normalize_box=VisualBboxRuntime.normalize_ocr_box,
            )
        )
        image_vision_runtime = ImageVisionRuntime(
            **parser_image_bundle_runtime.build_image_vision_kwargs(
                enabled=vision_enhance_enabled,
                vision_max_pages=vision_max_pages,
                vision_consecutive_fail_stop=vision_consecutive_fail_stop,
                resolve_api_key=resolve_api_key,
                select_low_quality_pages_for_vision=select_low_quality_pages_for_vision,
                vision_focus_from_page_lines=vision_focus_from_page_lines,
                render_page_png_for_vision=render_page_png_for_vision,
                extract_payload=extract_payload,
                extract_vision_insights=extract_vision_insights,
                append_ref=ReferenceRuntime.append_ref,
                build_tables_from_vision_payload=build_tables_from_vision_payload,
                build_figures_from_vision_payload=build_figures_from_vision_payload,
                merge_figure_blocks=merge_figure_blocks,
                augment_with_line_tables=augment_with_line_tables,
                next_table_index=BlockIndexRuntime.next_table_index,
                next_figure_index=BlockIndexRuntime.next_figure_index,
            )
        )
        image_parse_runtime = ImageParseRuntime(
            **parser_image_bundle_runtime.build_image_parse_kwargs(
                infer_tables_from_ocr_cells=infer_tables_from_ocr_cells,
                infer_tables_from_page_lines=infer_tables_from_page_lines,
                infer_figures_from_page_lines=infer_figures_from_page_lines,
                enhance_low_quality_pages_with_vision=enhance_low_quality_pages_with_vision,
                merge_figure_blocks=merge_figure_blocks,
                prune_fragment_tables=prune_fragment_tables,
            )
        )
        image_document_runtime = ImageDocumentRuntime(
            **parser_image_bundle_runtime.build_image_document_kwargs(
                vision_enhance_enabled=vision_enhance_enabled,
                visual_backend_available=visual_backend_available,
                resolve_api_key=resolve_api_key,
                get_ocr_engine=get_ocr_engine,
                collect_page_ocr=image_ocr_runtime.collect_page_ocr,
                build_parse_result=image_parse_runtime.build_parse_result,
            )
        )
        return {
            "_image_ocr_runtime": image_ocr_runtime,
            "_image_vision_runtime": image_vision_runtime,
            "_image_parse_runtime": image_parse_runtime,
            "_image_document_runtime": image_document_runtime,
        }
