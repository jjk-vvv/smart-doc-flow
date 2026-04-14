from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "core"
        / "format"
        / "plain_text_parser.py"
    )
    module_name = "_smart_doc_flow_module2_plain_text_parser"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


plain_text_parser = _load_module()
parse_plain_payload = plain_text_parser.parse_plain_payload
normalize_text = plain_text_parser.normalize_text
normalize_plain_line = plain_text_parser.normalize_plain_line
split_page_text = plain_text_parser.split_page_text


def _build_header_meta(headers: list[str]) -> list[dict]:
    return [
        {
            "col_index": idx,
            "raw": raw,
            "name": raw,
            "name_norm": raw.lower(),
            "unit": None,
        }
        for idx, raw in enumerate(headers, start=1)
    ]


def _decorate_rows_with_meta(rows_payload: list[dict], headers: list[str]) -> list[dict]:
    header_meta = _build_header_meta(headers)
    header_map = {int(item["col_index"]): item for item in header_meta}
    decorated: list[dict] = []
    row_idx = 1
    for row in rows_payload:
        cells: list[dict] = []
        for cell in row.get("cells", []):
            current = dict(cell)
            meta = header_map.get(int(cell.get("col_index", 0) or 0), {})
            current.update(
                {
                    "header": meta.get("name"),
                    "header_norm": meta.get("name_norm", ""),
                    "header_unit": meta.get("unit"),
                    "value_type": "text",
                    "numeric_value": None,
                    "ratio_value": None,
                    "detected_unit": None,
                    "normalized_text": str(cell.get("text", "")),
                }
            )
            cells.append(current)
        if cells:
            decorated.append(
                {
                    "row_index": row_idx,
                    "source_row_index": int(row.get("row_index", row_idx) or row_idx),
                    "cells": cells,
                }
            )
            row_idx += 1
    return decorated


def _looks_like_figure_cue_text(text: str) -> bool:
    normalized = str(text or "").lower()
    return any(token in normalized for token in ("figure", "chart", "趋势图", "图", "曲线"))


def test_plain_text_parser_normalizes_and_splits_blocks() -> None:
    text = "Alpha\t Beta\x00\n\n\nGamma"

    assert normalize_text(text) == "Alpha Beta \n\nGamma"
    assert split_page_text("One\n\n" + ("A" * 705), max_len=700) == ["One", "A" * 700, "A" * 5]


def test_plain_text_parser_keeps_headings_and_key_value_lines_as_separate_blocks() -> None:
    blocks = split_page_text(
        "# Report Title\n"
        "发布机构：国家统计局\n"
        "2025年2月28日\n\n"
        "第一段内容，用于说明统计公报的背景信息。第二段内容继续展开描述。",
        max_len=80,
    )

    assert blocks[0] == "# Report Title"
    assert blocks[1] == "发布机构：国家统计局"
    assert blocks[2] == "2025年2月28日"
    assert any("第一段内容" in block for block in blocks[3:])


def test_plain_text_parser_parses_markdown_tables_and_figures() -> None:
    payload = (
        "# Report\n\n"
        "| Region | Revenue |\n"
        "| --- | --- |\n"
        "| East | 100 |\n"
        "| West | 200 |\n\n"
        "![趋势图](trend.png)\n"
    ).encode("utf-8")

    result = parse_plain_payload(
        payload,
        ".md",
        table_max_rows=10,
        table_max_cols=6,
        nonpdf_figure_max=4,
        build_header_meta=_build_header_meta,
        decorate_rows_with_meta=_decorate_rows_with_meta,
        looks_like_figure_cue_text=_looks_like_figure_cue_text,
    )

    assert len(result.table_blocks) == 1
    assert result.table_blocks[0]["headers"] == ["Region", "Revenue"]
    assert result.table_blocks[0]["row_count"] == 2
    assert len(result.figure_blocks) == 1
    assert result.figure_blocks[0]["figure_type"] == "chart"
    assert result.figure_blocks[0]["key_points"] == ["trend.png"]
    assert 'ref id="md_t1_r1_c1"' in result.markdown
    assert 'ref id="md_fig_1"' in result.markdown


def test_plain_text_parser_parses_text_tables_and_figure_cues() -> None:
    payload = (
        "名称,数值,单位\n"
        "温度,25,℃\n"
        "压力,10,kPa\n"
        "流量,5,L/s\n\n"
        "图1 系统趋势图\n"
    ).encode("utf-8")

    result = parse_plain_payload(
        payload,
        ".txt",
        table_max_rows=10,
        table_max_cols=6,
        nonpdf_figure_max=4,
        build_header_meta=_build_header_meta,
        decorate_rows_with_meta=_decorate_rows_with_meta,
        looks_like_figure_cue_text=_looks_like_figure_cue_text,
    )

    assert len(result.table_blocks) == 1
    assert result.table_blocks[0]["headers"] == ["名称", "数值", "单位"]
    assert result.table_blocks[0]["row_count"] == 3
    assert len(result.figure_blocks) == 1
    assert result.figure_blocks[0]["caption"].startswith("图1")
    assert 'ref id="txt_t1_r1_c1"' in result.markdown
    assert 'ref id="txt_fig_1"' in result.markdown


def test_plain_text_parser_skips_noise_lines_and_normalizes_spaced_headings() -> None:
    blocks = split_page_text(
        "2024 [1]\n"
        "合肥市统计局 国家统计局合肥调查队\n"
        "2025 年3月28日\n"
        "一、综 合\n"
        "全年生产总值（GDP）[2]13507.69亿元。\n",
        max_len=120,
    )

    assert "2024 [1]" not in blocks
    assert blocks[0] == "合肥市统计局 国家统计局合肥调查队"
    assert blocks[1] == "2025年3月28日"
    assert blocks[2] == "一、综合"
    assert "全年生产总值（GDP）13507.69亿元。" in blocks[3]


def test_normalize_plain_line_strips_inline_footnotes() -> None:
    assert normalize_plain_line("全年生产总值（GDP）[2]13507.69亿元") == "全年生产总值（GDP）13507.69亿元"
