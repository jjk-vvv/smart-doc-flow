from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_visual_context_bootstrap_module = import_module("module2.app.core.parsers.parser_visual_context_bootstrap_runtime")
parser_visual_context_bundle_module = parser_visual_context_bootstrap_module

ParserVisualContextBootstrapRuntime = (
    parser_visual_context_bootstrap_module.ParserVisualContextBootstrapRuntime
)
ParserVisualContextBundleRuntime = parser_visual_context_bundle_module.ParserVisualContextBundleRuntime


def test_parser_visual_context_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserVisualContextBootstrapRuntime()

    attrs = runtime.build_visual_context_runtime_attrs(
        parser_visual_context_bundle_runtime=ParserVisualContextBundleRuntime(),
        image_extensions={".png", ".jpg"},
        native_text_threshold=48,
        visual_probe_pages=6,
        mineru_method="auto",
        mineru_scanned_method="ocr",
        mineru_method_fallbacks="txt,ocr",
        visual_first_max_pages_scanned=12,
        mineru_text_first_office_pdf_enable=True,
        mineru_text_first_office_pdf_min_pages=3,
        mineru_text_first_office_pdf_min_probe_chars=800,
        pdf_text_first_enable=True,
        pdf_text_heavy_min_probe_chars=1200,
        pdf_text_heavy_min_chars_per_page=300,
        pdf_text_heavy_max_visual_cues=3,
        pdf_mixed_text_pref_min_chars_per_page=120,
        pdf_mixed_text_pref_max_visual_cues=6,
        pdf_text_only_short_circuit_enable=True,
        visual_max_objects=24,
        visual_table_max_per_page=3,
        visual_figure_max_per_page=4,
        visual_figure_chart_score_min=6,
        visual_figure_cueless_fallback_max=2,
        visual_figure_refine_budget=4,
        visual_figure_refine_min_score=5,
        visual_runtime_large_doc_page_threshold=20,
        visual_runtime_large_doc_image_threshold=10,
        visual_runtime_large_doc_max_objects=18,
        visual_runtime_large_doc_figure_max_per_page=2,
        visual_runtime_large_doc_cueless_fallback_max=1,
        visual_runtime_large_doc_chart_score_min=7,
        visual_runtime_large_doc_refine_budget=2,
        visual_runtime_extreme_doc_page_threshold=40,
        visual_runtime_extreme_doc_max_objects=12,
        visual_runtime_extreme_doc_figure_max_per_page=1,
        visual_runtime_extreme_doc_cueless_fallback_max=0,
        visual_runtime_extreme_doc_chart_score_min=8,
        visual_runtime_extreme_doc_refine_budget=1,
        visual_first_max_pages=18,
        max_pages=40,
        visual_runtime_office_text_layout_page_cap=10,
        visual_runtime_mixed_text_layout_page_cap=8,
        visual_runtime_extreme_doc_layout_page_cap=6,
        visual_context_max_chars=1800,
        visual_figure_chart_only=True,
        visual_figure_allow_cueless_fallback=True,
        normalize_text=lambda text: str(text).strip(),
        split_page_text=lambda text: [str(text).strip()] if str(text).strip() else [],
        safe_text_list=lambda value, **kwargs: [str(item).strip() for item in (value if isinstance(value, list) else [value]) if str(item).strip()],
        infer_figure_type_from_text=lambda text: "chart" if "chart" in str(text).lower() else "other",
        looks_like_figure_cue_text=lambda text: "figure" in str(text).lower(),
    )

    expected_keys = {
        "_pdf_visual_profile_runtime",
        "_visual_runtime_limits_runtime",
        "_visual_status_builder_runtime",
        "_visual_pdf_bootstrap_runtime",
        "_visual_pdf_prepare_runtime",
        "_visual_object_context_runtime",
        "_visual_layout_selector_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_pdf_visual_profile_runtime"], "classify_pdf_visual_profile")
    assert hasattr(attrs["_visual_runtime_limits_runtime"], "resolve_visual_runtime_limits")
    assert hasattr(attrs["_visual_status_builder_runtime"], "build_status_fields")
    assert hasattr(attrs["_visual_pdf_bootstrap_runtime"], "bootstrap")
    assert hasattr(attrs["_visual_pdf_prepare_runtime"], "prepare_context")
    assert hasattr(attrs["_visual_object_context_runtime"], "build_visual_object_context")
    assert hasattr(attrs["_visual_layout_selector_runtime"], "prioritize_layout_objects")
    assert attrs["_visual_pdf_bootstrap_runtime"]._resolve_visual_runtime_limits.__self__ is attrs["_visual_runtime_limits_runtime"]
