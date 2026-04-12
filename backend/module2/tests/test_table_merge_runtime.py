from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.parsers.native_document_parser import NativeDocumentParser
from app.core.table.table_metadata import build_header_meta


def _build_parser() -> NativeDocumentParser:
    return NativeDocumentParser(max_pages=1)


def _make_row(page: int, row_index: int, y: float, values: List[str]) -> Dict[str, Any]:
    cells: List[Dict[str, Any]] = []
    for col_index, value in enumerate(values, start=1):
        cells.append(
            {
                "col_index": col_index,
                "text": value,
                "ref_id": f"p{page}_r{row_index}_c{col_index}",
                "bbox": [float(page), 0.12, float(y), 0.76, 0.08],
            }
        )
    return {
        "row_index": row_index,
        "source_row_index": row_index,
        "cells": cells,
    }


def _make_table(
    *,
    table_id: str,
    page: int,
    headers: List[str],
    rows: List[Dict[str, Any]],
    caption: str = "",
    source: str = "pdf_fitz",
) -> Dict[str, Any]:
    return {
        "table_id": table_id,
        "source": source,
        "page": page,
        "headers": headers,
        "header_meta": build_header_meta(headers),
        "rows": rows,
        "row_count": len(rows),
        "col_count": max(len(headers), max((len(row.get("cells", [])) for row in rows), default=0)),
        "caption": caption,
        "bbox_norm": [0.12, 0.08, 0.76, 0.84],
    }


def _row_texts(table: Dict[str, Any]) -> List[List[str]]:
    out: List[List[str]] = []
    for row in table.get("rows", []):
        values = []
        for cell in sorted(row.get("cells", []), key=lambda item: int(item.get("col_index", 0) or 0)):
            values.append(str(cell.get("text", "")))
        out.append(values)
    return out


def test_merge_cross_page_tables_repairs_low_signal_continuation_headers_without_dropping_first_row() -> None:
    parser = _build_parser()

    prev = _make_table(
        table_id="pdf_fitz_t18",
        page=20,
        headers=["Retail Category", "Sales Amount", "Year over Year Growth"],
        rows=[
            _make_row(20, 1, 0.80, ["Food", "457.51", "-22.7"]),
            _make_row(20, 2, 0.89, ["Drink", "54.03", "1.6"]),
        ],
        caption="Table 3 Retail Sales by Category",
    )
    curr = _make_table(
        table_id="pdf_fitz_t19",
        page=21,
        headers=["Communications", "219.51", "-11.0"],
        rows=[
            _make_row(21, 1, 0.10, ["Petroleum", "388.29", "9.2"]),
        ],
    )

    merged = parser._table_merge_runtime.merge_cross_page_tables([prev, curr])

    assert len(merged) == 2
    repaired = merged[1]
    assert repaired["headers"] == ["Retail Category", "Sales Amount", "Year over Year Growth"]
    assert repaired["caption"] == "Table 3 Retail Sales by Category"
    assert repaired["continuation_of"] == "pdf_fitz_t18"
    assert repaired["row_count"] == 2
    assert _row_texts(repaired)[0] == ["Communications", "219.51", "-11.0"]
    assert _row_texts(repaired)[1] == ["Petroleum", "388.29", "9.2"]
    first_row_cells = repaired["rows"][0]["cells"]
    assert first_row_cells[0]["header"] == "Retail Category"
    assert first_row_cells[1]["header"] == "Sales Amount"
    assert first_row_cells[2]["header"] == "Year over Year Growth"


def test_merge_cross_page_tables_still_merges_when_repeated_headers_are_clean() -> None:
    parser = _build_parser()

    prev = _make_table(
        table_id="pdf_fitz_t20",
        page=36,
        headers=["Region", "Export", "Import"],
        rows=[
            _make_row(36, 1, 0.81, ["Asia", "1726.6", "1304.5"]),
            _make_row(36, 2, 0.90, ["Europe", "863.0", "533.2"]),
        ],
        caption="Table 4 Trade by Region",
    )
    curr = _make_table(
        table_id="pdf_fitz_t21",
        page=37,
        headers=["Region", "Export", "Import"],
        rows=[
            _make_row(37, 1, 0.10, ["North America", "784.9", "168.9"]),
            _make_row(37, 2, 0.19, ["Oceania", "101.6", "188.2"]),
        ],
        caption="Table 4 Trade by Region",
    )

    merged = parser._table_merge_runtime.merge_cross_page_tables([prev, curr])

    assert len(merged) == 1
    combined = merged[0]
    assert combined["headers"] == ["Region", "Export", "Import"]
    assert combined["row_count"] == 4
    assert combined["page_span"] == [36, 37]
    assert _row_texts(combined)[-1] == ["Oceania", "101.6", "188.2"]


def test_merge_cross_page_tables_repairs_generic_header_continuation_from_first_data_row() -> None:
    parser = _build_parser()

    prev = _make_table(
        table_id="pdf_fitz_t9",
        page=23,
        headers=["类别", "计量单位", "绝对量", "比上年增长（%）"],
        rows=[
            _make_row(23, 1, 0.82, ["货物运输总量", "万吨", "45758.32", "-7.3"]),
            _make_row(23, 2, 0.90, ["公路", "万吨", "20834.34", "-14.7"]),
        ],
        caption="表 6 2022 年各种运输方式完成货物运输量情况",
        source="pdf_fitz",
    )
    curr = _make_table(
        table_id="pdf_fitz_t10",
        page=24,
        headers=["类别", "类别_2", "数值_1", "数值_2"],
        rows=[
            _make_row(24, 1, 0.09, ["民航", "万吨公里", "6511.91", "-23.1"]),
            _make_row(24, 2, 0.15, ["管道", "万吨公里", "495373.92", "1.9"]),
        ],
        source="pdf_fitz",
    )

    merged = parser._table_merge_runtime.merge_cross_page_tables([prev, curr])

    assert len(merged) == 2
    repaired = merged[1]
    assert repaired["headers"] == ["类别", "计量单位", "绝对量", "比上年增长（%）"]
    assert repaired["caption"] == "表 6 2022 年各种运输方式完成货物运输量情况"
    assert repaired["continuation_of"] == "pdf_fitz_t9"
    assert repaired["row_count"] == 2
    assert _row_texts(repaired) == [
        ["民航", "万吨公里", "6511.91", "-23.1"],
        ["管道", "万吨公里", "495373.92", "1.9"],
    ]


def test_merge_cross_page_tables_repairs_captionless_long_continuation_from_first_data_row() -> None:
    parser = _build_parser()

    prev = _make_table(
        table_id="pdf_fitz_t16",
        page=33,
        headers=["产品名称", "计量单位", "2021 年", "比上年增长（%）"],
        rows=[
            _make_row(33, 1, 0.64, ["水泥", "吨", "7316292", "-2.9"]),
            _make_row(33, 2, 0.72, ["生铁", "吨", "17487606", "0.2"]),
            _make_row(33, 3, 0.80, ["粗钢", "吨", "19626984", "0.2"]),
            _make_row(33, 4, 0.88, ["钢材", "吨", "18905168", "9.0"]),
        ],
        caption="表 2 2021 年主要工业产品产量情况",
        source="pdf_fitz",
    )
    curr = _make_table(
        table_id="pdf_fitz_t17",
        page=34,
        headers=["类别", "类别_2", "数值_1", "数值_2"],
        rows=[
            _make_row(34, 1, 0.09, ["新能源汽车", "辆", "50473", "119.1"]),
            _make_row(34, 2, 0.15, ["城市轨道车辆", "辆", "2204", "5.9"]),
            _make_row(34, 3, 0.21, ["民用钢质船舶", "载重吨", "105060", "-46.6"]),
            _make_row(34, 4, 0.27, ["光纤", "千米", "4893228", "-24.8"]),
            _make_row(34, 5, 0.33, ["光缆", "芯千米", "14220586", "10.1"]),
        ],
        source="pdf_fitz",
    )

    merged = parser._table_merge_runtime.merge_cross_page_tables([prev, curr])

    assert len(merged) == 2
    repaired = merged[1]
    assert repaired["headers"] == ["产品名称", "计量单位", "2021 年", "比上年增长（%）"]
    assert repaired["caption"] == "表 2 2021 年主要工业产品产量情况"
    assert repaired["continuation_of"] == "pdf_fitz_t16"
    assert repaired["row_count"] == 5
    assert _row_texts(repaired)[0] == ["新能源汽车", "辆", "50473", "119.1"]
