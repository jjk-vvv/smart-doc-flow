from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_docx_bootstrap_module = import_module("app.modules.module2.core.parsers.parser_docx_bootstrap_runtime")
parser_dispatch_bundle_module = parser_docx_bootstrap_module
parser_docx_content_bundle_module = parser_docx_bootstrap_module
parser_dependency_bundle_module = import_module("app.modules.module2.core.parsers.parser_bootstrap_runtime")

ParserDocxBootstrapRuntime = parser_docx_bootstrap_module.ParserDocxBootstrapRuntime
ParserDispatchBundleRuntime = parser_dispatch_bundle_module.ParserDispatchBundleRuntime
ParserDocxContentBundleRuntime = parser_docx_content_bundle_module.ParserDocxContentBundleRuntime
ParserDependencyBundleRuntime = parser_dependency_bundle_module.ParserDependencyBundleRuntime


def test_parser_docx_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserDocxBootstrapRuntime()
    dependency_runtime = ParserDependencyBundleRuntime()

    attrs = runtime.build_docx_runtime_attrs(
        parser_dispatch_bundle_runtime=ParserDispatchBundleRuntime(),
        parser_docx_content_bundle_runtime=ParserDocxContentBundleRuntime(),
        build_docx_enrichment_bundle=dependency_runtime.build_docx_enrichment_bundle,
        word_pdf_timeout_sec=30,
        word_pdf_parse_use_source_signals=True,
        word_pdf_docx_chart_xml_merge_enable=True,
        word_parse_via_pdf=True,
        office_convert_enabled=True,
        word_convert_allow_native_fallback=True,
        text_extensions={".txt"},
        image_extensions={".png"},
        artifact_root_dir=Path("artifacts"),
        docx_chart_xml_enable=True,
        docx_media_probe_enable=True,
        docx_media_max_assets=8,
        docx_media_vision_enable=True,
        docx_media_nested_gemini_enhance_enable=True,
        docx_media_max_assets_unbounded=False,
        docx_media_vision_max_assets=6,
        docx_media_vision_max_assets_unbounded=False,
        docx_media_vision_max_bytes=2_000_000,
        docx_media_vision_chart_only=True,
        docx_media_vision_allow_noncue=False,
        nonpdf_figure_max=4,
        normalize_text=lambda text: str(text).strip(),
        safe_text_list=lambda value, **kwargs: [
            str(item).strip()
            for item in (value if isinstance(value, list) else [value])
            if str(item).strip()
        ],
        looks_like_figure_cue_text=lambda text: "chart" in str(text).lower(),
        normalize_dataframe_headers=lambda headers, **kwargs: list(headers or []),
        normalize_dataframe_matrix=lambda rows, **kwargs: list(rows or []),
        decorate_rows_with_meta=lambda rows, headers: rows,
        build_header_meta=lambda headers: [{"name": item} for item in headers],
        parse_pdf=lambda *args, **kwargs: ("pdf-md", {}, []),
        parse_docx_via_pdf=lambda **kwargs: ("docx-pdf-md", {}, []),
        parse_docx=lambda file_bytes: ("docx-md", {}, []),
        parse_xlsx=lambda file_bytes: ("xlsx-md", {}, []),
        parse_plain=lambda file_bytes, ext=".txt": ("plain-md", {}, []),
        parse_image=lambda file_name, file_bytes: ("img-md", {}, []),
        get_last_figure_blocks=lambda: [],
        set_last_figure_blocks=lambda figure_blocks: None,
        convert_word_bytes_to_pdf=lambda **kwargs: (b"%PDF", {"converter": "stub", "elapsed_ms": 1}),
        consume_document=lambda **kwargs: ([], 1),
        merge_figure_blocks=lambda left, right: list(left or []) + list(right or []),
        consume_relaxed_root=lambda **kwargs: ([], 1),
        append_text_ref=lambda **kwargs: True,
        find_matching_pdf_figure_index=lambda **kwargs: None,
        table_block_to_dataframe=lambda table_block: ([], []),
    )

    expected_keys = {
        "_docx_via_pdf_runtime",
        "_document_dispatch_runtime",
        "_docx_enrichment",
        "_docx_document_runtime",
        "_docx_chart_merge_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_docx_via_pdf_runtime"], "parse_docx_via_pdf")
    assert hasattr(attrs["_document_dispatch_runtime"], "parse_document")
    assert hasattr(attrs["_docx_enrichment"], "extract_docx_chart_and_media")
    assert hasattr(attrs["_docx_document_runtime"], "parse_docx")
    assert hasattr(attrs["_docx_chart_merge_runtime"], "merge_docx_chart_xml_into_pdf_figures")
    assert attrs["_docx_document_runtime"]._extract_docx_chart_and_media.__self__ is attrs["_docx_enrichment"]
    assert attrs["_docx_chart_merge_runtime"]._extract_docx_chart_xml_tables.__self__ is attrs["_docx_enrichment"]
