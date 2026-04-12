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


rows_runtime_module = _load_module(
    ["module2", "app", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_table_rows_runtime",
)

NonPdfTableRowsRuntime = rows_runtime_module.NonPdfTableRowsRuntime


class _FakeCell:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeRow:
    def __init__(self, *cells: str) -> None:
        self.cells = [_FakeCell(text) for text in cells]


def test_nonpdf_table_rows_runtime_builds_rows_payload_and_refs() -> None:
    runtime = NonPdfTableRowsRuntime(normalize_text=lambda text: " ".join(str(text or "").split()))
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    rows_payload = runtime.build_rows_payload(
        table_id="docx_t1",
        rows=[_FakeRow(" 城市 ", "120"), _FakeRow("农村", "80")],
        get_cells=lambda row: row.cells,
        get_cell_text=lambda cell: cell.text,
        max_rows=10,
        max_cols=5,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert len(rows_payload) == 2
    assert rows_payload[0]["cells"][0]["text"] == "城市"
    assert rows_payload[0]["cells"][0]["ref_id"] == "docx_t1_r1_c1"
    assert "docx_t1_r1_c1" in bbox_map
    assert '<ref id="docx_t1_r1_c1">城市</ref>' in "".join(parts)


def test_nonpdf_table_rows_runtime_skips_empty_rows_and_respects_limits() -> None:
    runtime = NonPdfTableRowsRuntime(normalize_text=lambda text: str(text or "").strip())
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    rows_payload = runtime.build_rows_payload(
        table_id="docx_t2",
        rows=[_FakeRow("", ""), _FakeRow("A", "1"), _FakeRow("B", "2")],
        get_cells=lambda row: row.cells,
        get_cell_text=lambda cell: cell.text,
        max_rows=2,
        max_cols=1,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert len(rows_payload) == 1
    assert len(rows_payload[0]["cells"]) == 1
    assert rows_payload[0]["cells"][0]["text"] == "A"
    assert "docx_t2_r3_c1" not in bbox_map


def test_nonpdf_table_rows_runtime_builds_indexed_rows_payload_with_cap() -> None:
    runtime = NonPdfTableRowsRuntime(normalize_text=lambda text: str(text or "").strip())
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    rows_payload, emitted, hit_cap = runtime.build_indexed_rows_payload(
        rows=[("A", "1"), ("B", "2")],
        get_cells=lambda row: list(row),
        get_cell_text=lambda cell: cell,
        get_row_index=lambda row, row_pos: row_pos,
        get_col_index=lambda cell, cell_pos: cell_pos,
        build_cell_bbox=lambda row_idx, col_idx, cell: [1.0, float(col_idx), float(row_idx), 0.1, 0.1],
        build_cell_ref=lambda row_idx, col_idx, cell: f"xlsx_t1_r{row_idx}_c{col_idx}",
        max_rows=10,
        max_cols=10,
        emitted_cells=0,
        max_emitted_cells=2,
        parts=parts,
        bbox_map=bbox_map,
        break_on_col_overflow=True,
    )

    assert hit_cap is True
    assert emitted == 2
    assert len(rows_payload) == 1
    assert [cell["text"] for cell in rows_payload[0]["cells"]] == ["A", "1"]
    assert "xlsx_t1_r2_c1" not in bbox_map


def test_nonpdf_table_rows_runtime_builds_indexed_rows_payload_for_sparse_columns() -> None:
    runtime = NonPdfTableRowsRuntime(normalize_text=lambda text: str(text or "").strip())
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}
    seen_cols: list[int] = []

    rows = [
        [
            {"col": 1, "text": "地区"},
            {"col": 3, "text": "120"},
            {"col": 5, "text": "ignored"},
        ]
    ]

    rows_payload, emitted, hit_cap = runtime.build_indexed_rows_payload(
        rows=rows,
        get_cells=lambda row: row,
        get_cell_text=lambda cell: str(cell.get("text", "")),
        get_row_index=lambda row, row_pos: row_pos,
        get_col_index=lambda cell, cell_pos: int(cell.get("col", cell_pos) or cell_pos),
        build_cell_bbox=lambda row_idx, col_idx, cell: [1.0, float(col_idx), float(row_idx), 0.1, 0.1],
        build_cell_ref=lambda row_idx, col_idx, cell: f"xlsx_t2_r{row_idx}_c{col_idx}",
        max_rows=10,
        max_cols=3,
        emitted_cells=0,
        max_emitted_cells=10,
        parts=parts,
        bbox_map=bbox_map,
        after_cell=lambda row_idx, col_idx, cell, text: seen_cols.append(col_idx),
    )

    assert hit_cap is False
    assert emitted == 2
    assert len(rows_payload) == 1
    assert [cell["col_index"] for cell in rows_payload[0]["cells"]] == [1, 3]
    assert seen_cols == [1, 3]
    assert "xlsx_t2_r1_c5" not in bbox_map
