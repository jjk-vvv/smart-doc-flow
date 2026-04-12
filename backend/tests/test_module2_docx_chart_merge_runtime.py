from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


docx_chart_merge_runtime_module = _load_module(
    ["module2", "app", "core", "format", "docx_document_runtime.py"],
    "_smart_doc_flow_module2_docx_document_runtime_for_chart_merge",
)

DocxChartMergeRuntime = docx_chart_merge_runtime_module.DocxChartMergeRuntime


def test_docx_chart_merge_runtime_merges_chart_dataframe_into_matching_figure() -> None:
    runtime = DocxChartMergeRuntime(
        extract_docx_chart_xml_tables=lambda file_bytes: (
            [{"chart_title": "Revenue Trend", "table_id": "docx_chart_1"}],
            {"docx_chart_xml_seen": 1, "docx_chart_xml_parsed": 1},
        ),
        normalize_text=lambda text: " ".join(str(text or "").split()),
        find_matching_pdf_figure_index=lambda **kwargs: 0,
        table_block_to_dataframe=lambda table: (
            ["Quarter", "Revenue"],
            [["Q1", "10"], ["Q2", "20"]],
        ),
        safe_text_list=lambda values, max_items=8, max_len=180: [
            str(item).strip() for item in (values or []) if str(item).strip()
        ][:max_items],
    )

    result = runtime.merge_docx_chart_xml_into_pdf_figures(
        file_bytes=b"docx",
        figure_blocks=[
            {
                "figure_id": "pdf_figure_1",
                "caption": "Revenue Trend",
                "content_modes": ["text"],
                "quality": 0.4,
                "insights": ["existing note"],
            }
        ],
    )

    assert result["stats_patch"]["docx_chart_xml_seen"] == 1
    assert result["stats_patch"]["docx_chart_xml_parsed"] == 1
    assert result["stats_patch"]["docx_chart_xml_merged"] == 1
    assert result["stats_patch"]["docx_chart_xml_unmatched"] == 0
    figure = result["figure_blocks"][0]
    assert figure["dataframe"] == {
        "headers": ["Quarter", "Revenue"],
        "rows": [["Q1", "10"], ["Q2", "20"]],
    }
    assert figure["dataframe_source"] == "docx_chart_xml_merge"
    assert figure["content_modes"] == ["dataframe", "text", "visual"]
    assert figure["quality"] == 0.72
    assert figure["insights"] == ["existing note", "dataframe: 2x2"]


def test_docx_chart_merge_runtime_preserves_existing_dataframe_rows_without_counting_unmatched() -> None:
    runtime = DocxChartMergeRuntime(
        extract_docx_chart_xml_tables=lambda file_bytes: (
            [{"chart_title": "Revenue Trend"}],
            {"docx_chart_xml_seen": 1, "docx_chart_xml_parsed": 1},
        ),
        normalize_text=lambda text: " ".join(str(text or "").split()),
        find_matching_pdf_figure_index=lambda **kwargs: 0,
        table_block_to_dataframe=lambda table: (
            ["Quarter", "Revenue"],
            [["Q1", "10"]],
        ),
        safe_text_list=lambda values, max_items=8, max_len=180: [],
    )

    existing_figure = {
        "figure_id": "pdf_figure_1",
        "caption": "Revenue Trend",
        "dataframe": {"headers": ["Already"], "rows": [["keep"]]},
        "content_modes": ["dataframe", "visual"],
    }
    result = runtime.merge_docx_chart_xml_into_pdf_figures(
        file_bytes=b"docx",
        figure_blocks=[existing_figure],
    )

    assert result["stats_patch"]["docx_chart_xml_merged"] == 0
    assert result["stats_patch"]["docx_chart_xml_unmatched"] == 0
    assert result["figure_blocks"][0] == existing_figure


def test_docx_chart_merge_runtime_returns_extractor_stats_when_no_chart_tables_or_figures() -> None:
    runtime = DocxChartMergeRuntime(
        extract_docx_chart_xml_tables=lambda file_bytes: (
            [],
            {"docx_chart_xml_seen": 1, "docx_chart_xml_parsed": 0, "docx_chart_xml_merged": 0},
        ),
        normalize_text=lambda text: text,
        find_matching_pdf_figure_index=lambda **kwargs: None,
        table_block_to_dataframe=lambda table: ([], []),
        safe_text_list=lambda values, max_items=8, max_len=180: [],
    )

    result = runtime.merge_docx_chart_xml_into_pdf_figures(
        file_bytes=b"docx",
        figure_blocks=[],
    )

    assert result["figure_blocks"] == []
    assert result["stats_patch"] == {
        "docx_chart_xml_seen": 1,
        "docx_chart_xml_parsed": 0,
        "docx_chart_xml_merged": 0,
    }
