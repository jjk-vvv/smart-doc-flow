from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_pdf_bootstrap_module = import_module("module2.app.core.parsers.parser_pdf_bootstrap_runtime")
parser_dependency_bundle_module = import_module("module2.app.core.parsers.parser_bootstrap_runtime")

ParserPdfBootstrapRuntime = parser_pdf_bootstrap_module.ParserPdfBootstrapRuntime
ParserDependencyBundleRuntime = parser_dependency_bundle_module.ParserDependencyBundleRuntime


def test_parser_pdf_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserPdfBootstrapRuntime()

    attrs = runtime.build_pdf_runtime_attrs(
        parser_dependency_bundle_runtime=ParserDependencyBundleRuntime(),
        ocr_large_doc_dpi=144,
        ocr_large_doc_page_threshold=80,
        ocr_low_priority_dpi=96,
        ocr_high_priority_pages=3,
        ocr_dense_cue_threshold=12,
        ocr_max_attempt_pages_dense_cue=9,
        ocr_max_attempt_pages_mid_cue=6,
        ocr_dynamic_neighbor_pages=1,
        ocr_dynamic_neighbor_auto_enable=True,
        ocr_dynamic_neighbor_auto_max=4,
        ocr_min_pages_before_budget=2,
        ocr_front_scan_pages=5,
        ocr_low_cue_boost_enable=True,
        ocr_low_cue_min_pages_cap=3,
        ocr_time_budget_max_sec=60.0,
        ocr_time_budget_sec=12.0,
        ocr_time_budget_per_page=0.5,
        ocr_budget_guard_ratio=0.8,
        ocr_dynamic_early_stop_enable=True,
        ocr_dynamic_early_stop_min_pages=3,
        ocr_dynamic_early_stop_min_signal_pages=1,
        ocr_dynamic_early_stop_streak=2,
        ocr_relaxed_trigger_table_count=2,
        ocr_table_relaxed_min_quality=0.45,
        ocr_table_min_quality=0.55,
        ocr_uncovered_line_aug_pages=4,
        max_pages=40,
        max_pages_visual=20,
        visual_probe_pages=4,
        native_text_threshold=80,
        ocr_cue_scan_pages=6,
        enable_fitz_table=True,
        table_merge_enable=True,
        visual_force_ocr_on_weak_native=True,
        gemini_vision_enable_figures=True,
        get_ocr_engine=lambda: object(),
        set_runtime_page_count=lambda page_count: None,
        normalize_text=lambda text: str(text).strip(),
        split_page_text=lambda text: [str(text).strip()] if str(text).strip() else [],
        build_ocr_page_indices=lambda page_count, cue_pages=None: list(range(min(page_count, 2))),
        looks_like_table_cue_text=lambda text: "table" in str(text).lower(),
        infer_tables_from_ocr_cells=lambda *args, **kwargs: [],
        augment_with_line_tables=lambda base_tables, line_tables: list(base_tables or []) + list(line_tables or []),
        need_line_table_augmentation=lambda table_blocks, page_lines: False,
        select_line_augmentation_pages=lambda page_lines, base_tables, cue_pages=None: {},
        infer_tables_from_page_lines=lambda page_lines, parts, bbox_map, source_prefix: [],
        select_uncovered_table_like_pages=lambda page_lines, base_tables, aggressive=False: {},
        infer_figures_from_page_lines=lambda *args, **kwargs: [],
        get_last_figure_blocks=lambda: [],
        enhance_low_quality_pages_with_gemini_vision=lambda **kwargs: (kwargs["table_blocks"], []),
        merge_figure_blocks=lambda left, right: list(left or []) + list(right or []),
        prune_fragment_tables=lambda table_blocks: list(table_blocks or []),
        merge_same_page_tables=lambda table_blocks: list(table_blocks or []),
        merge_cross_page_tables=lambda table_blocks: list(table_blocks or []),
        collect_table_cue_pages=lambda reader, cue_scan_pages: [],
        extract_pdf_tables_with_fitz=lambda file_bytes, page_count, parts, bbox_map: [],
        is_weak_native_table_result=lambda tables, cue_pages: False,
        figure_blocks_need_vision=lambda figure_blocks: False,
    )

    expected_keys = {
        "_pdf_ocr_runtime",
        "_pdf_native_parse_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_pdf_ocr_runtime"], "parse_pdf_with_ocr")
    assert hasattr(attrs["_pdf_native_parse_runtime"], "parse_pdf_native")
    assert attrs["_pdf_ocr_runtime"].ocr_front_scan_pages == 5
    assert attrs["_pdf_native_parse_runtime"].max_pages == 40
