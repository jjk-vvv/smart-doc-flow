from __future__ import annotations

import importlib.util
import re
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


table_header_module = _load_module(
    ["app", "modules", "module2", "core", "table", "table_header_runtime.py"],
    "_smart_doc_flow_module2_table_header_runtime",
)

TableHeaderRuntime = table_header_module.TableHeaderRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _normalize_token_for_compare(text: str) -> str:
    normalized = _normalize_text(text).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)


def _contains_figure_marker(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(
        re.search(r"\bfig(?:ure)?\.?\s*[a-z0-9]", normalized, flags=re.IGNORECASE)
        or re.search(r"\btable\b", normalized, flags=re.IGNORECASE)
        or re.search(r"图\s*[0-9A-Za-z一二三四五六七八九十]", normalized)
    )


def _contains_catalog_marker(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    return any(token in normalized for token in ("catalog", "contents", "list")) or ("目录" in normalized)


def _is_unit_like_token(text: str) -> bool:
    value = _normalize_text(text).lower().strip("()[]{}<>（）【】")
    if not value:
        return False
    return value in {"kg", "g", "%", "℃", "°c", "万", "万元"} or bool(
        re.fullmatch(r"[a-z%\u00b0\u2103\u2109\u2030\u03bc/\-0-9]{1,16}", value)
    )


def _cell(col_index: int, text: str) -> dict[str, Any]:
    return {"col_index": col_index, "text": text, "ref_id": f"r{col_index}", "bbox": [1.0, 0.0, 0.0, 1.0, 1.0]}


def _row(*texts: str) -> dict[str, Any]:
    return {"row_index": 1, "cells": [_cell(idx, text) for idx, text in enumerate(texts, start=1)]}


def _build_runtime(*, page_count: int = 20) -> TableHeaderRuntime:
    return TableHeaderRuntime(
        normalize_text=_normalize_text,
        normalize_token_for_compare=_normalize_token_for_compare,
        contains_figure_marker=_contains_figure_marker,
        contains_catalog_marker=_contains_catalog_marker,
        runtime_page_count_provider=lambda: page_count,
    )


def test_table_header_runtime_recovers_headers_by_promoting_first_data_row() -> None:
    runtime = _build_runtime()

    headers, rows = runtime.recover_low_signal_headers(
        ["col_1", "col_2"],
        [_row("季度", "营收"), _row("Q1", "10")],
    )

    assert headers == ["季度", "营收"]
    assert len(rows) == 1
    assert rows[0]["cells"][0]["text"] == "Q1"


def test_table_header_runtime_recovers_geo_and_percent_headers_from_values() -> None:
    runtime = _build_runtime()

    headers, rows = runtime.recover_low_signal_headers(
        ["col_1", "col_2"],
        [_row("北京市", "25%"), _row("上海市", "75%")],
        caption="区域占比统计图",
    )

    assert headers == ["地区", "占比"]
    assert len(rows) == 2


def test_table_header_runtime_infers_headers_after_caption_row_and_unit_row() -> None:
    runtime = _build_runtime()

    headers, data_rows = runtime.infer_headers_and_data_rows(
        [
            _row("表1 销售统计"),
            _row("地区", "数量"),
            _row("", "kg"),
            _row("华东", "10"),
            _row("华南", "15"),
        ]
    )

    assert headers == ["地区", "数量 (kg)"]
    assert len(data_rows) == 2
    assert data_rows[0]["cells"][0]["text"] == "华东"


def test_table_header_runtime_drops_redundant_header_like_rows() -> None:
    runtime = _build_runtime()

    filtered = runtime.drop_redundant_header_like_rows(
        [_row("地区", "数量"), _row("华东", "10")],
        ["地区", "数量"],
    )

    assert len(filtered) == 1
    assert filtered[0]["cells"][0]["text"] == "华东"


def test_table_header_runtime_figure_axis_dimension_label_prefers_temporal_and_geo_columns() -> None:
    runtime = _build_runtime()

    assert runtime.figure_axis_dimension_label(["2021年", "2022年"]) == "年份"
    assert runtime.figure_axis_dimension_label(["北京市", "上海市"]) == "地区"
