from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_context_bundle_runtime_module = import_module("module2.app.core.parsers.parser_visual_context_bootstrap_runtime")

ParserVisualContextBundleRuntime = parser_visual_context_bundle_runtime_module.ParserVisualContextBundleRuntime


def test_parser_visual_context_bundle_runtime_builds_profile_and_limits_kwargs() -> None:
    runtime = ParserVisualContextBundleRuntime()

    normalize_text = lambda text: str(text).strip()

    profile_kwargs = runtime.build_pdf_visual_profile_kwargs(
        native_text_threshold=320,
        visual_probe_pages=6,
        mineru_method="auto",
        mineru_scanned_method="ocr",
        mineru_method_fallbacks="ocr,txt",
        visual_first_max_pages_scanned=40,
        mineru_text_first_office_pdf_enable=True,
        mineru_text_first_office_pdf_min_pages=12,
        mineru_text_first_office_pdf_min_probe_chars=800,
        pdf_text_first_enable=True,
        pdf_text_heavy_min_probe_chars=1400,
        pdf_text_heavy_min_chars_per_page=280,
        pdf_text_heavy_max_visual_cues=2,
        pdf_mixed_text_pref_min_chars_per_page=180,
        pdf_mixed_text_pref_max_visual_cues=5,
        pdf_text_only_short_circuit_enable=True,
        normalize_text=normalize_text,
    )
    limits_kwargs = runtime.build_visual_runtime_limits_kwargs(
        image_extensions={".png", ".jpg"},
        visual_max_objects=24,
        visual_table_max_per_page=4,
        visual_figure_max_per_page=3,
        visual_figure_chart_score_min=5,
        visual_figure_cueless_fallback_max=2,
        visual_figure_refine_budget=6,
        visual_figure_refine_min_score=4,
        visual_runtime_large_doc_page_threshold=80,
        visual_runtime_large_doc_image_threshold=12,
        visual_runtime_large_doc_max_objects=16,
        visual_runtime_large_doc_figure_max_per_page=2,
        visual_runtime_large_doc_cueless_fallback_max=1,
        visual_runtime_large_doc_chart_score_min=6,
        visual_runtime_large_doc_refine_budget=4,
        visual_runtime_extreme_doc_page_threshold=160,
        visual_runtime_extreme_doc_max_objects=12,
        visual_runtime_extreme_doc_figure_max_per_page=1,
        visual_runtime_extreme_doc_cueless_fallback_max=0,
        visual_runtime_extreme_doc_chart_score_min=7,
        visual_runtime_extreme_doc_refine_budget=2,
    )

    assert profile_kwargs["native_text_threshold"] == 320
    assert profile_kwargs["visual_probe_pages"] == 6
    assert profile_kwargs["mineru_method"] == "auto"
    assert profile_kwargs["mineru_method_fallbacks"] == "ocr,txt"
    assert profile_kwargs["pdf_text_only_short_circuit_enable"] is True
    assert profile_kwargs["normalize_text"]("  pdf  ") == "pdf"
    assert limits_kwargs["image_extensions"] == {".png", ".jpg"}
    assert limits_kwargs["visual_max_objects"] == 24
    assert limits_kwargs["visual_table_max_per_page"] == 4
    assert limits_kwargs["visual_figure_max_per_page"] == 3
    assert limits_kwargs["visual_runtime_extreme_doc_refine_budget"] == 2


def test_parser_visual_context_bundle_runtime_builds_bootstrap_and_prepare_kwargs() -> None:
    runtime = ParserVisualContextBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    summarize_pdf_metadata_signals = lambda reader: {"office_like": True}
    classify_pdf_visual_profile = lambda **kwargs: {"profile": "office_text_pdf"}
    resolve_visual_runtime_limits = lambda **kwargs: {"profile": "default", "max_objects": 24}
    split_page_text = lambda text: [text] if text else []
    append_ref = lambda parts, bbox_map, ref_id, text, bbox: parts.append(ref_id)

    bootstrap_kwargs = runtime.build_visual_pdf_bootstrap_kwargs(
        visual_probe_pages=6,
        visual_first_max_pages=40,
        max_pages=80,
        mineru_method="auto",
        visual_runtime_extreme_doc_page_threshold=160,
        visual_runtime_office_text_layout_page_cap=80,
        visual_runtime_mixed_text_layout_page_cap=40,
        visual_runtime_extreme_doc_layout_page_cap=20,
        normalize_text=normalize_text,
        summarize_pdf_metadata_signals=summarize_pdf_metadata_signals,
        classify_pdf_visual_profile=classify_pdf_visual_profile,
        resolve_visual_runtime_limits=resolve_visual_runtime_limits,
    )
    prepare_kwargs = runtime.build_visual_pdf_prepare_kwargs(
        normalize_text=normalize_text,
        split_page_text=split_page_text,
        append_ref=append_ref,
    )

    assert bootstrap_kwargs["visual_probe_pages"] == 6
    assert bootstrap_kwargs["visual_first_max_pages"] == 40
    assert bootstrap_kwargs["max_pages"] == 80
    assert bootstrap_kwargs["mineru_method"] == "auto"
    assert bootstrap_kwargs["summarize_pdf_metadata_signals"](None) == {"office_like": True}
    assert bootstrap_kwargs["classify_pdf_visual_profile"]() == {"profile": "office_text_pdf"}
    assert bootstrap_kwargs["resolve_visual_runtime_limits"]() == {"profile": "default", "max_objects": 24}
    assert prepare_kwargs["normalize_text"]("  text  ") == "text"
    assert prepare_kwargs["split_page_text"]("page text") == ["page text"]
    assert prepare_kwargs["append_ref"]([], {}, "p1", "text", [1.0, 0.0, 0.0, 1.0, 1.0]) is None


def test_parser_visual_context_bundle_runtime_builds_object_context_and_layout_selector_kwargs() -> None:
    runtime = ParserVisualContextBundleRuntime()

    normalize_text = lambda text: str(text).strip()
    safe_text_list = lambda items, **kwargs: [str(item).strip() for item in (items or []) if str(item).strip()]
    infer_figure_type_from_text = lambda text: "chart"
    contains_table_marker = lambda text: "table" in str(text).lower()
    contains_figure_marker = lambda text: "figure" in str(text).lower()
    looks_like_figure_cue_text = lambda text: "chart" in str(text).lower()

    object_context_kwargs = runtime.build_visual_object_context_kwargs(
        visual_context_max_chars=2400,
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
    )
    layout_selector_kwargs = runtime.build_visual_layout_selector_kwargs(
        visual_max_objects=24,
        visual_table_max_per_page=4,
        visual_figure_max_per_page=3,
        visual_figure_chart_score_min=5,
        visual_figure_cueless_fallback_max=2,
        visual_figure_chart_only=True,
        visual_figure_allow_cueless_fallback=True,
        normalize_text=normalize_text,
        safe_text_list=safe_text_list,
        infer_figure_type_from_text=infer_figure_type_from_text,
        contains_table_marker=contains_table_marker,
        contains_figure_marker=contains_figure_marker,
        looks_like_figure_cue_text=looks_like_figure_cue_text,
    )

    assert object_context_kwargs["visual_context_max_chars"] == 2400
    assert object_context_kwargs["normalize_text"]("  obj  ") == "obj"
    assert object_context_kwargs["safe_text_list"]([" a ", "", "b"]) == ["a", "b"]
    assert layout_selector_kwargs["visual_max_objects"] == 24
    assert layout_selector_kwargs["visual_table_max_per_page"] == 4
    assert layout_selector_kwargs["visual_figure_chart_only"] is True
    assert layout_selector_kwargs["visual_figure_allow_cueless_fallback"] is True
    assert layout_selector_kwargs["infer_figure_type_from_text"]("sales chart") == "chart"
    assert layout_selector_kwargs["contains_table_marker"]("table 1") is True
    assert layout_selector_kwargs["contains_figure_marker"]("Figure 2") is True
    assert layout_selector_kwargs["looks_like_figure_cue_text"]("chart trend") is True
