from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


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


table_merge_module = _load_module(
    ["module2", "app", "core", "table", "table_merge_runtime.py"],
    "_smart_doc_flow_module2_table_merge_runtime",
)

TableMergeRuntime = table_merge_module.TableMergeRuntime


def _drop_redundant_header_like_rows(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    normalized_headers = [str(item or "").strip().lower() for item in headers]
    out: list[dict[str, Any]] = []
    for row in rows_payload:
        values = [
            str(cell.get("text", "") or "").strip().lower()
            for cell in sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
        ]
        if values[: len(normalized_headers)] == normalized_headers[: len(values)]:
            continue
        out.append(row)
    return out


def _build_runtime() -> TableMergeRuntime:
    return TableMergeRuntime(
        table_merge_max_page_gap=1,
        table_merge_header_sim=0.58,
        table_merge_col_overlap=0.55,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        normalize_token_for_compare=lambda text: "".join(ch.lower() for ch in str(text or "") if ch.isalnum()),
        is_page_number_token=lambda text: str(text or "").strip().isdigit(),
        drop_redundant_header_like_rows=_drop_redundant_header_like_rows,
    )


def _cell(text: str, *, col_index: int, y: float) -> dict[str, Any]:
    return {
        "col_index": col_index,
        "text": text,
        "bbox": [1.0, 0.0, y, 0.1, 0.04],
    }


def _row(*cells: dict[str, Any]) -> dict[str, Any]:
    return {"cells": list(cells)}


def test_table_merge_runtime_merges_same_page_fragments() -> None:
    runtime = _build_runtime()

    result = runtime.merge_same_page_tables(
        [
            {
                "table_id": "t1",
                "source": "pdf_native",
                "page": 1,
                "headers": ["Year", "Revenue"],
                "rows": [
                    _row(_cell("2023", col_index=1, y=0.10), _cell("100", col_index=2, y=0.10)),
                    _row(_cell("2024", col_index=1, y=0.16), _cell("120", col_index=2, y=0.16)),
                ],
                "row_count": 2,
                "col_count": 2,
                "quality": 0.8,
            },
            {
                "table_id": "t2",
                "source": "pdf_native",
                "page": 1,
                "headers": ["Year", "Revenue"],
                "rows": [
                    _row(_cell("2025", col_index=1, y=0.22), _cell("140", col_index=2, y=0.22)),
                ],
                "row_count": 1,
                "col_count": 2,
                "quality": 0.6,
            },
        ]
    )

    assert len(result) == 1
    assert result[0]["row_count"] == 3
    assert result[0]["merged_from"] == ["t1", "t2"]


def test_table_merge_runtime_merges_cross_page_tables_and_drops_repeated_header_row() -> None:
    runtime = _build_runtime()

    result = runtime.merge_cross_page_tables(
        [
            {
                "table_id": "t1",
                "source": "pdf_native",
                "page": 1,
                "headers": ["Table 2 Revenue", "Amount"],
                "rows": [
                    _row(_cell("North", col_index=1, y=0.82), _cell("100", col_index=2, y=0.82)),
                ],
                "row_count": 1,
                "col_count": 2,
                "quality": 0.8,
            },
            {
                "table_id": "t2",
                "source": "pdf_native",
                "page": 2,
                "headers": ["Table 2 Revenue", "Amount"],
                "rows": [
                    _row(_cell("Table 2 Revenue", col_index=1, y=0.10), _cell("Amount", col_index=2, y=0.10)),
                    _row(_cell("South", col_index=1, y=0.16), _cell("120", col_index=2, y=0.16)),
                ],
                "row_count": 2,
                "col_count": 2,
                "quality": 0.6,
            },
        ]
    )

    assert len(result) == 1
    assert result[0]["page"] == 1
    assert result[0]["page_span"] == [1, 2]
    assert result[0]["row_count"] == 2
    assert [row["cells"][0]["text"] for row in result[0]["rows"]] == ["North", "South"]


def test_table_merge_runtime_keeps_distinct_tables_separate_when_overlap_is_weak() -> None:
    runtime = _build_runtime()

    result = runtime.merge_cross_page_tables(
        [
            {
                "table_id": "t1",
                "source": "pdf_native",
                "page": 1,
                "headers": ["Year", "Revenue", "Margin", "Region"],
                "rows": [_row(_cell("2024", col_index=1, y=0.82), _cell("100", col_index=2, y=0.82))],
                "row_count": 1,
                "col_count": 4,
            },
            {
                "table_id": "t2",
                "source": "pdf_native",
                "page": 2,
                "headers": ["Quarter", "Cash"],
                "rows": [_row(_cell("Q1", col_index=1, y=0.10), _cell("80", col_index=2, y=0.10))],
                "row_count": 1,
                "col_count": 2,
            },
        ]
    )

    assert len(result) == 2
