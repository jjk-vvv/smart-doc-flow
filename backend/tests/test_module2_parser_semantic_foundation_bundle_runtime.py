from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_semantic_foundation_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_semantic_bootstrap_runtime")

ParserSemanticFoundationBundleRuntime = parser_semantic_foundation_bundle_runtime_module.ParserSemanticFoundationBundleRuntime


def test_parser_semantic_foundation_bundle_runtime_builds_figure_and_pruning_kwargs() -> None:
    runtime = ParserSemanticFoundationBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    header_token_is_generic = lambda text: str(text).lower().startswith("col_")
    contains_section_marker = lambda text: "section" in str(text).lower()

    figure_text_kwargs = runtime.build_figure_text_kwargs(
        normalize_text=normalize_text,
        header_token_is_generic=header_token_is_generic,
    )
    table_pruning_kwargs = runtime.build_table_pruning_kwargs(
        normalize_text=normalize_text,
        contains_section_marker=contains_section_marker,
        header_token_is_generic=header_token_is_generic,
    )

    assert figure_text_kwargs["normalize_text"]("  x  ") == "x"
    assert figure_text_kwargs["header_token_is_generic"]("col_1") is True
    assert table_pruning_kwargs["normalize_text"]("  y  ") == "y"
    assert table_pruning_kwargs["contains_section_marker"]("section 1") is True
    assert table_pruning_kwargs["header_token_is_generic"]("col_2") is True


def test_parser_semantic_foundation_bundle_runtime_builds_figure_inference_and_content_kwargs() -> None:
    runtime = ParserSemanticFoundationBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()
    contains_figure_marker = lambda text: "figure" in str(text).lower()
    contains_catalog_marker = lambda text: "catalog" in str(text).lower()
    strip_figure_caption_noise = lambda text: str(text).replace("Figure 1:", "").strip()
    count_figure_markers_in_text = lambda text: 1
    next_figure_index = lambda blocks, prefix: 4

    figure_inference_kwargs = runtime.build_figure_inference_kwargs(
        vision_enable_figures=True,
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        contains_figure_marker=contains_figure_marker,
        contains_catalog_marker=contains_catalog_marker,
        strip_figure_caption_noise=strip_figure_caption_noise,
        count_figure_markers_in_text=count_figure_markers_in_text,
        next_figure_index=next_figure_index,
    )
    content_kwargs = runtime.build_content_normalization_kwargs(
        normalize_text=normalize_text,
    )

    assert figure_inference_kwargs["vision_enable_figures"] is True
    assert figure_inference_kwargs["normalize_text"]("  fig  ") == "fig"
    assert figure_inference_kwargs["normalize_token_for_compare"]("ABC") == "abc"
    assert figure_inference_kwargs["contains_figure_marker"]("Figure 1") is True
    assert figure_inference_kwargs["contains_catalog_marker"]("catalog page") is True
    assert figure_inference_kwargs["strip_figure_caption_noise"]("Figure 1: Sales") == "Sales"
    assert figure_inference_kwargs["count_figure_markers_in_text"]("Figure 1") == 1
    assert figure_inference_kwargs["next_figure_index"]([], "pdf_f") == 4
    assert content_kwargs["normalize_text"]("  dataframe  ") == "dataframe"
