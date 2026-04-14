from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_docx_content_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_docx_bootstrap_runtime")

ParserDocxContentBundleRuntime = parser_docx_content_bundle_runtime_module.ParserDocxContentBundleRuntime


def test_parser_docx_content_bundle_runtime_builds_docx_document_kwargs() -> None:
    runtime = ParserDocxContentBundleRuntime()

    consume_document = lambda **kwargs: ([{"table_id": "t1"}], 2)
    extract_docx_chart_and_media = lambda **kwargs: (
        [{"figure_id": "f1"}],
        [{"table_id": "t2"}],
        {"ok": True},
        3,
    )
    merge_figure_blocks = lambda current, extra: current + extra
    consume_relaxed_root = lambda **kwargs: ([{"table_id": "relaxed"}], 1)
    append_text_ref = lambda **kwargs: True

    kwargs = runtime.build_docx_document_kwargs(
        nonpdf_figure_max=8,
        consume_document=consume_document,
        extract_docx_chart_and_media=extract_docx_chart_and_media,
        merge_figure_blocks=merge_figure_blocks,
        consume_relaxed_root=consume_relaxed_root,
        append_text_ref=append_text_ref,
    )

    assert kwargs["nonpdf_figure_max"] == 8
    assert kwargs["consume_document"]() == ([{"table_id": "t1"}], 2)
    assert kwargs["extract_docx_chart_and_media"]() == (
        [{"figure_id": "f1"}],
        [{"table_id": "t2"}],
        {"ok": True},
        3,
    )
    assert kwargs["merge_figure_blocks"]([{"figure_id": "a"}], [{"figure_id": "b"}]) == [
        {"figure_id": "a"},
        {"figure_id": "b"},
    ]
    assert kwargs["consume_relaxed_root"]() == ([{"table_id": "relaxed"}], 1)
    assert kwargs["append_text_ref"]() is True


def test_parser_docx_content_bundle_runtime_builds_docx_chart_merge_kwargs() -> None:
    runtime = ParserDocxContentBundleRuntime()

    extract_docx_chart_xml_tables = lambda file_bytes: ([{"chart_title": "Sales"}], {"count": 1})
    normalize_text = lambda text: str(text).strip()
    find_matching_pdf_figure_index = lambda **kwargs: 0
    table_block_to_dataframe = lambda table: (["A", "B"], [["1", "2"]])
    safe_text_list = lambda items, **kwargs: [str(item).strip() for item in (items or []) if str(item).strip()]

    kwargs = runtime.build_docx_chart_merge_kwargs(
        extract_docx_chart_xml_tables=extract_docx_chart_xml_tables,
        normalize_text=normalize_text,
        find_matching_pdf_figure_index=find_matching_pdf_figure_index,
        table_block_to_dataframe=table_block_to_dataframe,
        safe_text_list=safe_text_list,
    )

    assert kwargs["extract_docx_chart_xml_tables"](b"docx") == ([{"chart_title": "Sales"}], {"count": 1})
    assert kwargs["normalize_text"]("  chart  ") == "chart"
    assert kwargs["find_matching_pdf_figure_index"](chart_title="Sales", figure_blocks=[]) == 0
    assert kwargs["table_block_to_dataframe"]({"table_id": "t1"}) == (["A", "B"], [["1", "2"]])
    assert kwargs["safe_text_list"]([" a ", "", "b"]) == ["a", "b"]
