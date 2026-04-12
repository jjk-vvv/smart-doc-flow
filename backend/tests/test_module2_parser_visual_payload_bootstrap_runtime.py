from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_payload_bootstrap_module = import_module("module2.app.core.parsers.parser_visual_payload_bootstrap_runtime")
parser_visual_payload_bundle_module = parser_visual_payload_bootstrap_module
content_normalization_module = import_module("module2.app.core.schema.content_normalization_runtime")
figure_semantics_module = import_module("module2.app.core.visual.figure_semantics")
figure_inference_module = import_module("module2.app.core.visual.figure_inference")
table_header_module = import_module("module2.app.core.table.table_header_runtime")

ParserVisualPayloadBootstrapRuntime = parser_visual_payload_bootstrap_module.ParserVisualPayloadBootstrapRuntime
ParserVisualPayloadBundleRuntime = parser_visual_payload_bundle_module.ParserVisualPayloadBundleRuntime
ContentNormalizationRuntime = content_normalization_module.ContentNormalizationRuntime
FigureTextRuntime = figure_semantics_module.FigureTextRuntime
FigureInferenceRuntime = figure_inference_module.FigureInferenceRuntime
TableHeaderRuntime = table_header_module.TableHeaderRuntime


def test_parser_visual_payload_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserVisualPayloadBootstrapRuntime()
    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()

    table_header = TableHeaderRuntime(
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        contains_figure_marker=lambda text: "fig" in str(text).lower(),
        contains_catalog_marker=lambda text: "catalog" in str(text).lower(),
        runtime_page_count_provider=lambda: 5,
    )
    figure_text_runtime = FigureTextRuntime(
        normalize_text=normalize_text,
        header_token_is_generic=TableHeaderRuntime.header_token_is_generic,
    )
    figure_inference = FigureInferenceRuntime(
        gemini_vision_enable_figures=True,
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        contains_figure_marker=lambda text: "fig" in str(text).lower(),
        contains_catalog_marker=lambda text: "catalog" in str(text).lower(),
        strip_figure_caption_noise=figure_text_runtime.strip_figure_caption_noise,
        count_figure_markers_in_text=figure_text_runtime.count_figure_markers_in_text,
        next_figure_index=lambda figure_blocks: len(list(figure_blocks or [])) + 1,
    )
    content_normalization_runtime = ContentNormalizationRuntime(
        normalize_text=normalize_text,
    )

    attrs = runtime.build_visual_payload_runtime_attrs(
        parser_visual_payload_bundle_runtime=ParserVisualPayloadBundleRuntime(),
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        content_normalization_runtime=content_normalization_runtime,
        figure_text_runtime=figure_text_runtime,
        figure_inference=figure_inference,
        figure_text_is_low_signal=figure_text_runtime.figure_text_is_low_signal,
        table_header=table_header,
        looks_like_false_table=lambda headers, rows: False,
        gemini_vision_enable_figures=True,
        gemini_vision_max_figures_per_page=4,
        gemini_vision_min_figure_quality=0.65,
        gemini_vision_max_tables_per_page=3,
        gemini_vision_max_pages=12,
        gemini_vision_min_table_quality=0.63,
        table_max_cols=12,
        table_max_rows=80,
        table_cell_cap=2000,
        ocr_table_min_rows=2,
        ocr_cue_max_pages=180,
        visual_weak_table_min=3,
        visual_weak_table_quality=0.48,
        visual_use_table_html_fallback=True,
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
    )

    expected_keys = {
        "_figure_semantics",
        "_figure_vision_payload",
        "_visual_figure_builder",
        "_table_payload",
        "_table_vision_payload",
        "_visual_table_builder",
        "_visual_table_cue_runtime",
        "_visual_page_signal_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_figure_semantics"], "coerce_figure_dataframe")
    assert hasattr(attrs["_figure_vision_payload"], "build_figures_from_vision_payload")
    assert hasattr(attrs["_visual_figure_builder"], "build_figure_from_visual_payload")
    assert hasattr(attrs["_table_payload"], "vision_table_to_matrix")
    assert hasattr(attrs["_table_vision_payload"], "build_tables_from_vision_payload")
    assert hasattr(attrs["_visual_table_builder"], "build_table_from_visual_payload")
    assert hasattr(attrs["_visual_table_cue_runtime"], "collect_table_cue_pages")
    assert hasattr(attrs["_visual_page_signal_runtime"], "select_low_quality_pages_for_vision")
