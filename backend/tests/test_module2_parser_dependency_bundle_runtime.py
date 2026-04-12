from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_dependency_bundle_runtime_module = import_module("module2.app.core.parsers.parser_bootstrap_runtime")

ParserDependencyBundleRuntime = parser_dependency_bundle_runtime_module.ParserDependencyBundleRuntime


def test_parser_dependency_bundle_runtime_builds_pdf_ocr_bundle_and_wraps_last_figure_blocks() -> None:
    runtime = ParserDependencyBundleRuntime()
    calls: list[dict[str, object]] = []

    bundle = runtime.build_pdf_ocr_bundle(
        ocr_large_doc_dpi=200,
        ocr_large_doc_page_threshold=10,
        ocr_low_priority_dpi=150,
        ocr_high_priority_pages=4,
        ocr_dense_cue_threshold=3,
        ocr_max_attempt_pages_dense_cue=12,
        ocr_max_attempt_pages_mid_cue=8,
        ocr_dynamic_neighbor_pages=2,
        ocr_dynamic_neighbor_auto_enable=True,
        ocr_dynamic_neighbor_auto_max=5,
        ocr_min_pages_before_budget=3,
        ocr_front_scan_pages=6,
        ocr_low_cue_boost_enable=True,
        ocr_low_cue_min_pages_cap=7,
        ocr_time_budget_max_sec=90.0,
        ocr_time_budget_sec=60.0,
        ocr_time_budget_per_page=3.0,
        ocr_budget_guard_ratio=0.8,
        ocr_dynamic_early_stop_enable=True,
        ocr_dynamic_early_stop_min_pages=4,
        ocr_dynamic_early_stop_min_signal_pages=2,
        ocr_dynamic_early_stop_streak=3,
        ocr_relaxed_trigger_table_count=1,
        ocr_table_relaxed_min_quality=0.45,
        ocr_table_min_quality=0.55,
        ocr_uncovered_line_aug_pages=2,
        get_ocr_engine=lambda: "engine",
        set_runtime_page_count=lambda page_count: page_count,
        normalize_text=lambda text: text.strip(),
        normalize_box=lambda box: box,
        build_ocr_page_indices=lambda *args, **kwargs: {},
        looks_like_table_cue_text=lambda text: True,
        infer_tables_from_ocr_cells=lambda *args, **kwargs: [],
        augment_with_line_tables=lambda *args, **kwargs: [],
        need_line_table_augmentation=lambda *args, **kwargs: False,
        select_line_augmentation_pages=lambda *args, **kwargs: [],
        infer_tables_from_page_lines=lambda *args, **kwargs: [],
        select_uncovered_table_like_pages=lambda *args, **kwargs: [],
        infer_figures_from_page_lines=lambda page_lines, parts, bbox_map, source_prefix, last_figure_blocks: calls.append(
            {
                "page_lines": page_lines,
                "parts": parts,
                "bbox_map": bbox_map,
                "source_prefix": source_prefix,
                "last_figure_blocks": last_figure_blocks,
            }
        )
        or [{"figure_id": "f1"}],
        get_last_figure_blocks=lambda: [{"figure_id": "seed"}],
        enhance_low_quality_pages_with_gemini_vision=lambda *args, **kwargs: ([], []),
        merge_figure_blocks=lambda *args, **kwargs: [],
        prune_fragment_tables=lambda blocks: blocks,
    )

    assert bundle.config_kwargs["ocr_large_doc_dpi"] == 200
    assert bundle.config_kwargs["ocr_table_min_quality"] == 0.55

    figures = bundle.callback_kwargs["infer_figures_from_page_lines"](
        {1: ["row"]},
        ["part"],
        {"ref": [1.0, 0.0, 0.0, 1.0, 1.0]},
        "pdf_ocr",
    )

    assert figures == [{"figure_id": "f1"}]
    assert calls == [
        {
            "page_lines": {1: ["row"]},
            "parts": ["part"],
            "bbox_map": {"ref": [1.0, 0.0, 0.0, 1.0, 1.0]},
            "source_prefix": "pdf_ocr",
            "last_figure_blocks": [{"figure_id": "seed"}],
        }
    ]


def test_parser_dependency_bundle_runtime_builds_pdf_native_and_docx_enrichment_bundles() -> None:
    runtime = ParserDependencyBundleRuntime()

    pdf_native_bundle = runtime.build_pdf_native_bundle(
        max_pages=30,
        max_pages_visual=12,
        visual_probe_pages=4,
        native_text_threshold=80,
        ocr_cue_scan_pages=6,
        enable_fitz_table=True,
        table_merge_enable=True,
        visual_force_ocr_on_weak_native=False,
        gemini_vision_enable_figures=True,
        normalize_text=lambda text: text,
        split_page_text=lambda text: [text],
        append_ref=lambda *args, **kwargs: "ref",
        collect_table_cue_pages=lambda *args, **kwargs: [1],
        extract_pdf_tables_with_fitz=lambda *args, **kwargs: [],
        is_weak_native_table_result=lambda *args, **kwargs: False,
        select_line_augmentation_pages=lambda *args, **kwargs: [],
        infer_tables_from_page_lines=lambda *args, **kwargs: [],
        augment_with_line_tables=lambda *args, **kwargs: [],
        merge_same_page_tables=lambda blocks: blocks,
        merge_cross_page_tables=lambda blocks: blocks,
        infer_figures_from_page_lines=lambda *args, **kwargs: [],
        figure_blocks_need_vision=lambda *args, **kwargs: False,
        enhance_low_quality_pages_with_gemini_vision=lambda *args, **kwargs: ([], []),
        merge_figure_blocks=lambda *args, **kwargs: [],
        prune_fragment_tables=lambda blocks: blocks,
    )
    docx_bundle = runtime.build_docx_enrichment_bundle(
        artifact_root_dir=Path("artifacts"),
        image_extensions={".png", ".jpg"},
        docx_chart_xml_enable=True,
        docx_media_probe_enable=True,
        docx_media_max_assets=10,
        docx_media_vision_enable=True,
        docx_media_nested_gemini_enhance_enable=False,
        docx_media_max_assets_unbounded=False,
        docx_media_vision_max_assets=5,
        docx_media_vision_max_assets_unbounded=False,
        docx_media_vision_max_bytes=1024,
        docx_media_vision_chart_only=True,
        docx_media_vision_allow_noncue=False,
        nonpdf_figure_max=8,
        normalize_text=lambda text: text,
        safe_text_list=lambda items: list(items),
        looks_like_figure_cue_text=lambda text: True,
        normalize_dataframe_headers=lambda headers: headers,
        normalize_dataframe_matrix=lambda rows: rows,
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
        parse_image=lambda *args, **kwargs: ("md", {}, []),
        get_last_figure_blocks=lambda: [{"figure_id": "f1"}],
        set_last_figure_blocks=lambda blocks: blocks,
    )

    assert pdf_native_bundle.config_kwargs == {
        "max_pages": 30,
        "max_pages_visual": 12,
        "visual_probe_pages": 4,
        "native_text_threshold": 80,
        "ocr_cue_scan_pages": 6,
        "enable_fitz_table": True,
        "table_merge_enable": True,
        "visual_force_ocr_on_weak_native": False,
        "gemini_vision_enable_figures": True,
    }
    assert pdf_native_bundle.callback_kwargs["append_ref"]("x") == "ref"
    assert docx_bundle.config_kwargs["artifact_root_dir"] == Path("artifacts")
    assert docx_bundle.config_kwargs["image_extensions"] == {".png", ".jpg"}
    assert docx_bundle.callback_kwargs["get_last_figure_blocks"]() == [{"figure_id": "f1"}]
