from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_semantic_bootstrap_module = import_module("module2.app.core.parsers.parser_semantic_bootstrap_runtime")
parser_ocr_table_inference_bundle_module = parser_semantic_bootstrap_module
parser_semantic_foundation_bundle_module = parser_semantic_bootstrap_module
table_header_module = import_module("module2.app.core.table.table_header_runtime")

ParserSemanticBootstrapRuntime = parser_semantic_bootstrap_module.ParserSemanticBootstrapRuntime
ParserOcrTableInferenceBundleRuntime = (
    parser_ocr_table_inference_bundle_module.ParserOcrTableInferenceBundleRuntime
)
ParserSemanticFoundationBundleRuntime = (
    parser_semantic_foundation_bundle_module.ParserSemanticFoundationBundleRuntime
)
TableHeaderRuntime = table_header_module.TableHeaderRuntime


def test_parser_semantic_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserSemanticBootstrapRuntime()
    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()

    table_header = TableHeaderRuntime(
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        contains_figure_marker=lambda text: "fig" in str(text).lower(),
        contains_catalog_marker=lambda text: "catalog" in str(text).lower(),
        runtime_page_count_provider=lambda: 5,
    )

    attrs = runtime.build_semantic_runtime_attrs(
        parser_ocr_table_inference_bundle_runtime=ParserOcrTableInferenceBundleRuntime(),
        parser_semantic_foundation_bundle_runtime=ParserSemanticFoundationBundleRuntime(),
        ocr_table_min_quality=0.55,
        ocr_table_min_cols=2,
        ocr_table_min_rows=2,
        ocr_table_row_tol=0.05,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        ocr_table_relaxed_row_gap_scale=1.2,
        ocr_table_relaxed_align_min=0.3,
        ocr_table_relaxed_overlap_min=0.2,
        ocr_table_relaxed_col_diff_max=2,
        table_max_rows=80,
        table_max_cols=12,
        table_cell_cap=2000,
        table_merge_enable=True,
        gemini_vision_enable_figures=True,
        runtime_page_count_provider=lambda: 5,
        infer_headers_and_data_rows=table_header.infer_headers_and_data_rows,
        drop_redundant_header_like_rows=table_header.drop_redundant_header_like_rows,
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
        looks_like_false_table=lambda headers, rows: False,
        merge_same_page_tables=lambda tables: list(tables or []),
        merge_cross_page_tables=lambda tables: list(tables or []),
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
        group_table_rows=lambda cells, **kwargs: [cells],
        split_group_by_row_gaps=lambda group, **kwargs: [group],
        expand_group_with_sparse_rows=lambda *args, **kwargs: [],
        table_quality_score=lambda *args, **kwargs: 0.9,
    )

    expected_keys = {
        "_ocr_table_inference",
        "_figure_text_runtime",
        "_table_pruning_runtime",
        "_figure_inference",
        "_content_normalization_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_ocr_table_inference"], "infer_tables_from_ocr_cells")
    assert hasattr(attrs["_figure_text_runtime"], "strip_figure_caption_noise")
    assert hasattr(attrs["_table_pruning_runtime"], "prune_fragment_tables")
    assert hasattr(attrs["_figure_inference"], "infer_figures_from_page_lines")
    assert hasattr(attrs["_content_normalization_runtime"], "normalize_dataframe_headers")
    assert attrs["_ocr_table_inference"].ocr_table_min_quality == 0.55
    assert attrs["_figure_inference"].gemini_vision_enable_figures is True
