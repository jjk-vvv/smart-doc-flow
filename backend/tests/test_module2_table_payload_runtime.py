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


table_payload_module = _load_module(
    ["app", "modules", "module2", "core", "table", "table_payload_runtime.py"],
    "_smart_doc_flow_module2_table_payload_runtime",
)

TablePayloadRuntime = table_payload_module.TablePayloadRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values[:max_items]:
        text = _normalize_text(str(item or ""))
        if text:
            out.append(text[:max_len])
    return out


def _normalize_token_for_compare(text: str) -> str:
    normalized = _normalize_text(text).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)


def _headers_need_recovery(headers: list[str]) -> bool:
    normalized = [_normalize_text(item).lower() for item in headers if _normalize_text(item)]
    if not normalized:
        return True
    generic = {"col_1", "col_2", "col_3", "value", "metric", "category"}
    return any(item in generic for item in normalized)


def _build_runtime() -> TablePayloadRuntime:
    return TablePayloadRuntime(
        table_max_cols=6,
        table_max_rows=6,
        normalize_text=_normalize_text,
        safe_text_list=_safe_text_list,
        normalize_token_for_compare=_normalize_token_for_compare,
        headers_need_recovery=_headers_need_recovery,
    )


def test_table_payload_runtime_merges_header_rows_when_primary_headers_are_generic() -> None:
    runtime = _build_runtime()

    headers = runtime.extract_headers_from_table_payload(
        {
            "headers": ["col_1", "col_2"],
            "header_rows": [
                ["季度", "营收"],
                ["季度", "营收"],
            ],
        }
    )

    assert headers == ["季度", "营收"]


def test_table_payload_runtime_extracts_rows_and_html_table_matrix() -> None:
    runtime = _build_runtime()

    rows = runtime.extract_rows_from_table_payload(
        {
            "rows": [
                [" Q1 ", "10"],
                {"cells": ["Q2", "20"]},
                {"b": "30", "a": "Q3", "row_index": 3},
            ]
        }
    )
    html_matrix = runtime.matrix_from_html_table(
        "<table><tr><th>季度</th><th>营收</th></tr><tr><td>Q1</td><td>10</td></tr></table>"
    )

    assert rows == [["Q1", "10"], ["Q2", "20"], ["Q3", "30"]]
    assert html_matrix == [["季度", "营收"], ["Q1", "10"]]


def test_table_payload_runtime_builds_vision_table_matrix_with_non_generic_headers() -> None:
    runtime = _build_runtime()

    matrix = runtime.vision_table_to_matrix(
        {
            "headers": ["季度", "营收"],
            "rows": [["Q1", "10"], ["Q2", "20"]],
        }
    )

    assert matrix == [["季度", "营收"], ["Q1", "10"], ["Q2", "20"]]
