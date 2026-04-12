from __future__ import annotations

import importlib.util
import sys
import types
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


pdf_fitz_table_runtime_module = _load_module(
    ["module2", "app", "core", "pdf", "pdf_fitz_table_runtime.py"],
    "_smart_doc_flow_module2_pdf_fitz_table_runtime",
)

PdfFitzTableRuntime = pdf_fitz_table_runtime_module.PdfFitzTableRuntime


class _FakeTable:
    def __init__(self, matrix: list[list[str | None]], bbox: list[float]):
        self._matrix = matrix
        self.bbox = bbox

    def extract(self) -> list[list[str | None]]:
        return self._matrix


class _FakeFinder:
    def __init__(self, tables: list[_FakeTable]):
        self.tables = tables


class _FakeRect:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


class _FakePage:
    def __init__(self, tables: list[_FakeTable], *, width: float = 100.0, height: float = 200.0):
        self._tables = tables
        self.rect = _FakeRect(width=width, height=height)

    def find_tables(self) -> _FakeFinder:
        return _FakeFinder(self._tables)


class _FakeDoc:
    def __init__(self, pages: list[_FakePage]):
        self._pages = pages
        self.closed = False

    def __len__(self) -> int:
        return len(self._pages)

    def load_page(self, page_idx: int) -> _FakePage:
        return self._pages[page_idx]

    def close(self) -> None:
        self.closed = True


def _build_header_meta(headers: list[str]) -> list[dict[str, Any]]:
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


def _decorate_rows_with_meta(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    header_meta = _build_header_meta(headers)
    header_map = {int(item["col_index"]): item for item in header_meta}
    out: list[dict[str, Any]] = []
    for row in rows_payload:
        cells_out: list[dict[str, Any]] = []
        for cell in row.get("cells", []):
            current = dict(cell)
            meta = header_map.get(int(cell.get("col_index", 0) or 0), {})
            current["header"] = meta.get("name")
            current["header_norm"] = meta.get("name_norm", "")
            current["header_unit"] = meta.get("unit")
            cells_out.append(current)
        if cells_out:
            out.append(
                {
                    "row_index": int(row.get("row_index", 0) or 0),
                    "source_row_index": int(row.get("row_index", 0) or 0),
                    "cells": cells_out,
                }
            )
    return out


def _build_runtime(state: dict[str, Any], *, table_merge_enable: bool = True) -> PdfFitzTableRuntime:
    def _merge_same_page_tables(table_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        state["same_page_merge_calls"] = int(state.get("same_page_merge_calls", 0) or 0) + 1
        return table_blocks

    def _merge_cross_page_tables(table_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        state["cross_page_merge_calls"] = int(state.get("cross_page_merge_calls", 0) or 0) + 1
        return table_blocks

    return PdfFitzTableRuntime(
        table_max_rows=6,
        table_max_cols=4,
        table_cell_cap=24,
        table_merge_enable=table_merge_enable,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        decorate_rows_with_meta=_decorate_rows_with_meta,
        build_header_meta=_build_header_meta,
        merge_same_page_tables=_merge_same_page_tables,
        merge_cross_page_tables=_merge_cross_page_tables,
    )


def test_pdf_fitz_table_runtime_extracts_tables_and_refs(monkeypatch) -> None:
    fake_doc = _FakeDoc(
        [
            _FakePage(
                [
                    _FakeTable(
                        [
                            ["Region", "Revenue"],
                            ["East", "100"],
                            ["West", "200"],
                        ],
                        [10.0, 20.0, 60.0, 120.0],
                    )
                ]
            )
        ]
    )
    monkeypatch.setitem(sys.modules, "fitz", types.SimpleNamespace(open=lambda **kwargs: fake_doc))
    state: dict[str, Any] = {}
    runtime = _build_runtime(state)
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    result = runtime.extract_pdf_tables_with_fitz(
        file_bytes=b"%PDF-1.4 fake",
        page_count=1,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert fake_doc.closed is True
    assert state["same_page_merge_calls"] == 1
    assert state["cross_page_merge_calls"] == 1
    assert len(result) == 1
    assert result[0]["table_id"] == "pdf_fitz_t1"
    assert result[0]["source"] == "pdf_fitz"
    assert result[0]["headers"] == ["Region", "Revenue"]
    assert result[0]["row_count"] == 2
    assert result[0]["col_count"] == 2
    assert result[0]["rows"][0]["cells"][0]["header"] == "Region"
    assert 'ref id="pdf_fitz_t1_r1_c1"' in parts[0]
    assert bbox_map["pdf_fitz_t1_r1_c1"] == [1.0, 0.1, 0.1, 0.5, 0.5]


def test_pdf_fitz_table_runtime_returns_empty_when_open_fails(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "fitz",
        types.SimpleNamespace(open=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("open failed"))),
    )
    runtime = _build_runtime({}, table_merge_enable=False)

    result = runtime.extract_pdf_tables_with_fitz(
        file_bytes=b"%PDF-1.4 fake",
        page_count=1,
        parts=[],
        bbox_map={},
    )

    assert result == []


def test_pdf_fitz_table_runtime_can_skip_merge_for_prefill(monkeypatch) -> None:
    fake_doc = _FakeDoc(
        [
            _FakePage(
                [
                    _FakeTable(
                        [
                            ["Region", "Revenue"],
                            ["East", "100"],
                        ],
                        [10.0, 20.0, 60.0, 120.0],
                    )
                ]
            )
        ]
    )
    monkeypatch.setitem(sys.modules, "fitz", types.SimpleNamespace(open=lambda **kwargs: fake_doc))
    state: dict[str, Any] = {}
    runtime = _build_runtime(state)

    result = runtime.extract_pdf_tables_with_fitz(
        file_bytes=b"%PDF-1.4 fake",
        page_count=1,
        parts=[],
        bbox_map={},
        merge_tables=False,
    )

    assert len(result) == 1
    assert state.get("same_page_merge_calls", 0) == 0
    assert state.get("cross_page_merge_calls", 0) == 0


def test_pdf_fitz_table_runtime_normalize_table_bbox_handles_invalid_input() -> None:
    assert PdfFitzTableRuntime.normalize_table_bbox(None, 100.0, 200.0) == (0.0, 0.0, 1.0, 1.0)
    assert PdfFitzTableRuntime.normalize_table_bbox(["a", 0, 1, 1], 100.0, 200.0) == (0.0, 0.0, 1.0, 1.0)
