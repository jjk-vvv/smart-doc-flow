from __future__ import annotations

from typing import Any, Callable, Dict

from ..visual.figure_semantics import FigureSemanticsRuntime
from ..visual.figure_vision_payload import FigureVisionPayloadRuntime
from ..table.ocr_table_utils import OcrTableUtils
from ..table.table_payload_runtime import TablePayloadRuntime
from ..table.table_vision_payload import TableVisionPayloadRuntime
from ..visual.visual_planning_runtime import VisualPageSignalRuntime, VisualTableCueRuntime
from ..visual.visual_payload_builder import VisualBboxRuntime, VisualFigureBuilderRuntime, VisualTableBuilderRuntime
from ..schema.reference_runtime import ReferenceRuntime


RuntimeCallback = Callable[..., Any]


class ParserVisualPayloadBundleRuntime:
    """Build pure kwargs for parser-owned visual payload and signal runtimes."""

    def build_figure_semantics_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        figure_text_is_low_signal: RuntimeCallback,
        strip_figure_caption_noise: RuntimeCallback,
        header_token_is_generic: RuntimeCallback,
        normalize_dataframe_headers: RuntimeCallback,
        normalize_dataframe_matrix: RuntimeCallback,
        figure_axis_dimension_label: RuntimeCallback,
        headers_need_recovery: RuntimeCallback,
        recover_low_signal_headers: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "figure_text_is_low_signal": figure_text_is_low_signal,
            "strip_figure_caption_noise": strip_figure_caption_noise,
            "header_token_is_generic": header_token_is_generic,
            "normalize_dataframe_headers": normalize_dataframe_headers,
            "normalize_dataframe_matrix": normalize_dataframe_matrix,
            "figure_axis_dimension_label": figure_axis_dimension_label,
            "headers_need_recovery": headers_need_recovery,
            "recover_low_signal_headers": recover_low_signal_headers,
        }

    def build_figure_vision_payload_kwargs(
        self,
        *,
        vision_enable_figures: bool,
        vision_max_figures_per_page: int,
        vision_min_figure_quality: float,
        normalize_text: RuntimeCallback,
        infer_figure_type_from_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        figure_text_is_low_signal: RuntimeCallback,
        normalize_dataframe_headers: RuntimeCallback,
        normalize_dataframe_matrix: RuntimeCallback,
        normalize_figure_key_values: RuntimeCallback,
        coerce_figure_dataframe: RuntimeCallback,
        recover_figure_title_and_caption: RuntimeCallback,
        to_float_or_none: RuntimeCallback,
        count_figure_markers_in_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_enable_figures": vision_enable_figures,
            "vision_max_figures_per_page": vision_max_figures_per_page,
            "vision_min_figure_quality": vision_min_figure_quality,
            "normalize_text": normalize_text,
            "infer_figure_type_from_text": infer_figure_type_from_text,
            "safe_text_list": safe_text_list,
            "figure_text_is_low_signal": figure_text_is_low_signal,
            "normalize_dataframe_headers": normalize_dataframe_headers,
            "normalize_dataframe_matrix": normalize_dataframe_matrix,
            "normalize_figure_key_values": normalize_figure_key_values,
            "coerce_figure_dataframe": coerce_figure_dataframe,
            "recover_figure_title_and_caption": recover_figure_title_and_caption,
            "to_float_or_none": to_float_or_none,
            "count_figure_markers_in_text": count_figure_markers_in_text,
        }

    def build_visual_figure_builder_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        infer_figure_type_from_text: RuntimeCallback,
        figure_text_is_low_signal: RuntimeCallback,
        normalize_dataframe_headers: RuntimeCallback,
        normalize_dataframe_matrix: RuntimeCallback,
        normalize_figure_key_values: RuntimeCallback,
        coerce_figure_dataframe: RuntimeCallback,
        recover_figure_title_and_caption: RuntimeCallback,
        count_figure_markers_in_text: RuntimeCallback,
        to_float_or_none: RuntimeCallback,
        append_ref: RuntimeCallback,
        layout_bbox_to_ref_bbox: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
            "infer_figure_type_from_text": infer_figure_type_from_text,
            "figure_text_is_low_signal": figure_text_is_low_signal,
            "normalize_dataframe_headers": normalize_dataframe_headers,
            "normalize_dataframe_matrix": normalize_dataframe_matrix,
            "normalize_figure_key_values": normalize_figure_key_values,
            "coerce_figure_dataframe": coerce_figure_dataframe,
            "recover_figure_title_and_caption": recover_figure_title_and_caption,
            "count_figure_markers_in_text": count_figure_markers_in_text,
            "to_float_or_none": to_float_or_none,
            "append_ref": append_ref,
            "layout_bbox_to_ref_bbox": layout_bbox_to_ref_bbox,
        }

    def build_table_payload_kwargs(
        self,
        *,
        table_max_cols: int,
        table_max_rows: int,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        headers_need_recovery: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_max_cols": table_max_cols,
            "table_max_rows": table_max_rows,
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
            "normalize_token_for_compare": normalize_token_for_compare,
            "headers_need_recovery": headers_need_recovery,
        }

    def build_table_vision_payload_kwargs(
        self,
        *,
        vision_max_tables_per_page: int,
        table_max_rows: int,
        table_max_cols: int,
        ocr_table_min_rows: int,
        vision_table_to_matrix: RuntimeCallback,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        infer_headers_and_data_rows: RuntimeCallback,
        recover_low_signal_headers: RuntimeCallback,
        drop_redundant_header_like_rows: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        looks_like_false_table: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        to_float_or_none: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_max_tables_per_page": vision_max_tables_per_page,
            "table_max_rows": table_max_rows,
            "table_max_cols": table_max_cols,
            "ocr_table_min_rows": ocr_table_min_rows,
            "vision_table_to_matrix": vision_table_to_matrix,
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
            "infer_headers_and_data_rows": infer_headers_and_data_rows,
            "recover_low_signal_headers": recover_low_signal_headers,
            "drop_redundant_header_like_rows": drop_redundant_header_like_rows,
            "decorate_rows_with_meta": decorate_rows_with_meta,
            "looks_like_false_table": looks_like_false_table,
            "build_header_meta": build_header_meta,
            "to_float_or_none": to_float_or_none,
        }

    def build_visual_table_builder_kwargs(
        self,
        *,
        visual_use_table_html_fallback: bool,
        table_max_cols: int,
        table_max_rows: int,
        table_cell_cap: int,
        ocr_table_min_rows: int,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        to_float_or_none: RuntimeCallback,
        append_ref: RuntimeCallback,
        layout_bbox_to_ref_bbox: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        extract_headers_from_table_payload: RuntimeCallback,
        extract_rows_from_table_payload: RuntimeCallback,
        matrix_from_html_table: RuntimeCallback,
        recover_low_signal_headers: RuntimeCallback,
        looks_like_false_table: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "visual_use_table_html_fallback": visual_use_table_html_fallback,
            "table_max_cols": table_max_cols,
            "table_max_rows": table_max_rows,
            "table_cell_cap": table_cell_cap,
            "ocr_table_min_rows": ocr_table_min_rows,
            "normalize_text": normalize_text,
            "safe_text_list": safe_text_list,
            "to_float_or_none": to_float_or_none,
            "append_ref": append_ref,
            "layout_bbox_to_ref_bbox": layout_bbox_to_ref_bbox,
            "build_header_meta": build_header_meta,
            "decorate_rows_with_meta": decorate_rows_with_meta,
            "extract_headers_from_table_payload": extract_headers_from_table_payload,
            "extract_rows_from_table_payload": extract_rows_from_table_payload,
            "matrix_from_html_table": matrix_from_html_table,
            "recover_low_signal_headers": recover_low_signal_headers,
            "looks_like_false_table": looks_like_false_table,
        }

    def build_visual_table_cue_kwargs(
        self,
        *,
        ocr_cue_max_pages: int,
        visual_weak_table_min: int,
        visual_weak_table_quality: float,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "ocr_cue_max_pages": ocr_cue_max_pages,
            "visual_weak_table_min": visual_weak_table_min,
            "visual_weak_table_quality": visual_weak_table_quality,
            "normalize_text": normalize_text,
        }

    def build_visual_page_signal_kwargs(
        self,
        *,
        vision_max_pages: int,
        vision_min_table_quality: float,
        vision_enable_figures: bool,
        looks_like_table_cue_text: RuntimeCallback,
        looks_like_figure_cue_text: RuntimeCallback,
        contains_figure_marker: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_max_pages": vision_max_pages,
            "vision_min_table_quality": vision_min_table_quality,
            "vision_enable_figures": vision_enable_figures,
            "looks_like_table_cue_text": looks_like_table_cue_text,
            "looks_like_figure_cue_text": looks_like_figure_cue_text,
            "contains_figure_marker": contains_figure_marker,
        }


class ParserVisualPayloadBootstrapRuntime:
    """Build visual payload and signal runtimes so parser.py does not keep this constructor wiring inline."""

    def build_visual_payload_runtime_attrs(
        self,
        *,
        parser_visual_payload_bundle_runtime: Any,
        normalize_text: Callable[[str], str],
        normalize_token_for_compare: Callable[[str], str],
        content_normalization_runtime: Any,
        figure_text_runtime: Any,
        figure_inference: Any,
        figure_text_is_low_signal: Callable[..., bool],
        table_header: Any,
        looks_like_false_table: Callable[..., bool],
        vision_enable_figures: bool,
        vision_max_figures_per_page: int,
        vision_min_figure_quality: float,
        vision_max_tables_per_page: int,
        vision_max_pages: int,
        vision_min_table_quality: float,
        table_max_cols: int,
        table_max_rows: int,
        table_cell_cap: int,
        ocr_table_min_rows: int,
        ocr_cue_max_pages: int,
        visual_weak_table_min: int,
        visual_weak_table_quality: float,
        visual_use_table_html_fallback: bool,
        decorate_rows_with_meta: Callable[..., Any],
        build_header_meta: Callable[..., Any],
    ) -> Dict[str, Any]:
        figure_semantics = FigureSemanticsRuntime(
            **parser_visual_payload_bundle_runtime.build_figure_semantics_kwargs(
                normalize_text=normalize_text,
                figure_text_is_low_signal=figure_text_runtime.figure_text_is_low_signal,
                strip_figure_caption_noise=figure_text_runtime.strip_figure_caption_noise,
                header_token_is_generic=table_header.header_token_is_generic,
                normalize_dataframe_headers=content_normalization_runtime.normalize_dataframe_headers,
                normalize_dataframe_matrix=content_normalization_runtime.normalize_dataframe_matrix,
                figure_axis_dimension_label=table_header.figure_axis_dimension_label,
                headers_need_recovery=table_header.headers_need_recovery,
                recover_low_signal_headers=table_header.recover_low_signal_headers,
            )
        )
        figure_vision_payload = FigureVisionPayloadRuntime(
            **parser_visual_payload_bundle_runtime.build_figure_vision_payload_kwargs(
                vision_enable_figures=vision_enable_figures,
                vision_max_figures_per_page=vision_max_figures_per_page,
                vision_min_figure_quality=vision_min_figure_quality,
                normalize_text=normalize_text,
                infer_figure_type_from_text=figure_inference.infer_figure_type_from_text,
                safe_text_list=content_normalization_runtime.safe_text_list,
                figure_text_is_low_signal=figure_text_runtime.figure_text_is_low_signal,
                normalize_dataframe_headers=content_normalization_runtime.normalize_dataframe_headers,
                normalize_dataframe_matrix=content_normalization_runtime.normalize_dataframe_matrix,
                normalize_figure_key_values=figure_inference.normalize_figure_key_values,
                coerce_figure_dataframe=figure_semantics.coerce_figure_dataframe,
                recover_figure_title_and_caption=figure_semantics.recover_figure_title_and_caption,
                to_float_or_none=content_normalization_runtime.to_float_or_none,
                count_figure_markers_in_text=figure_text_runtime.count_figure_markers_in_text,
            )
        )
        visual_figure_builder = VisualFigureBuilderRuntime(
            **parser_visual_payload_bundle_runtime.build_visual_figure_builder_kwargs(
                normalize_text=normalize_text,
                safe_text_list=content_normalization_runtime.safe_text_list,
                infer_figure_type_from_text=figure_inference.infer_figure_type_from_text,
                figure_text_is_low_signal=figure_text_runtime.figure_text_is_low_signal,
                normalize_dataframe_headers=content_normalization_runtime.normalize_dataframe_headers,
                normalize_dataframe_matrix=content_normalization_runtime.normalize_dataframe_matrix,
                normalize_figure_key_values=figure_inference.normalize_figure_key_values,
                coerce_figure_dataframe=figure_semantics.coerce_figure_dataframe,
                recover_figure_title_and_caption=figure_semantics.recover_figure_title_and_caption,
                count_figure_markers_in_text=figure_text_runtime.count_figure_markers_in_text,
                to_float_or_none=content_normalization_runtime.to_float_or_none,
                append_ref=ReferenceRuntime.append_ref,
                layout_bbox_to_ref_bbox=VisualBboxRuntime.layout_bbox_to_ref_bbox,
            )
        )
        table_payload = TablePayloadRuntime(
            **parser_visual_payload_bundle_runtime.build_table_payload_kwargs(
                table_max_cols=table_max_cols,
                table_max_rows=table_max_rows,
                normalize_text=normalize_text,
                safe_text_list=content_normalization_runtime.safe_text_list,
                normalize_token_for_compare=normalize_token_for_compare,
                headers_need_recovery=table_header.headers_need_recovery,
            )
        )
        table_vision_payload = TableVisionPayloadRuntime(
            **parser_visual_payload_bundle_runtime.build_table_vision_payload_kwargs(
                vision_max_tables_per_page=vision_max_tables_per_page,
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                ocr_table_min_rows=ocr_table_min_rows,
                vision_table_to_matrix=table_payload.vision_table_to_matrix,
                normalize_text=normalize_text,
                safe_text_list=content_normalization_runtime.safe_text_list,
                infer_headers_and_data_rows=table_header.infer_headers_and_data_rows,
                recover_low_signal_headers=table_header.recover_low_signal_headers,
                drop_redundant_header_like_rows=table_header.drop_redundant_header_like_rows,
                decorate_rows_with_meta=decorate_rows_with_meta,
                looks_like_false_table=looks_like_false_table,
                build_header_meta=build_header_meta,
                to_float_or_none=content_normalization_runtime.to_float_or_none,
            )
        )
        visual_table_builder = VisualTableBuilderRuntime(
            **parser_visual_payload_bundle_runtime.build_visual_table_builder_kwargs(
                visual_use_table_html_fallback=visual_use_table_html_fallback,
                table_max_cols=table_max_cols,
                table_max_rows=table_max_rows,
                table_cell_cap=table_cell_cap,
                ocr_table_min_rows=ocr_table_min_rows,
                normalize_text=normalize_text,
                safe_text_list=content_normalization_runtime.safe_text_list,
                to_float_or_none=content_normalization_runtime.to_float_or_none,
                append_ref=ReferenceRuntime.append_ref,
                layout_bbox_to_ref_bbox=VisualBboxRuntime.layout_bbox_to_ref_bbox,
                build_header_meta=build_header_meta,
                decorate_rows_with_meta=decorate_rows_with_meta,
                extract_headers_from_table_payload=table_payload.extract_headers_from_table_payload,
                extract_rows_from_table_payload=table_payload.extract_rows_from_table_payload,
                matrix_from_html_table=table_payload.matrix_from_html_table,
                recover_low_signal_headers=table_header.recover_low_signal_headers,
                looks_like_false_table=looks_like_false_table,
            )
        )
        visual_table_cue_runtime = VisualTableCueRuntime(
            **parser_visual_payload_bundle_runtime.build_visual_table_cue_kwargs(
                ocr_cue_max_pages=ocr_cue_max_pages,
                visual_weak_table_min=visual_weak_table_min,
                visual_weak_table_quality=visual_weak_table_quality,
                normalize_text=normalize_text,
            )
        )
        visual_page_signal_runtime = VisualPageSignalRuntime(
            **parser_visual_payload_bundle_runtime.build_visual_page_signal_kwargs(
                vision_max_pages=vision_max_pages,
                vision_min_table_quality=vision_min_table_quality,
                vision_enable_figures=vision_enable_figures,
                looks_like_table_cue_text=visual_table_cue_runtime.looks_like_table_cue_text,
                looks_like_figure_cue_text=figure_inference.looks_like_figure_cue_text,
                contains_figure_marker=OcrTableUtils.contains_figure_marker,
            )
        )
        return {
            "_figure_semantics": figure_semantics,
            "_figure_vision_payload": figure_vision_payload,
            "_visual_figure_builder": visual_figure_builder,
            "_table_payload": table_payload,
            "_table_vision_payload": table_vision_payload,
            "_visual_table_builder": visual_table_builder,
            "_visual_table_cue_runtime": visual_table_cue_runtime,
            "_visual_page_signal_runtime": visual_page_signal_runtime,
        }
