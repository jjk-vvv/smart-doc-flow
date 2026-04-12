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


content_normalization_module = _load_module(
    ["module2", "app", "core", "schema", "content_normalization_runtime.py"],
    "_smart_doc_flow_module2_content_normalization_runtime",
)

ContentNormalizationRuntime = content_normalization_module.ContentNormalizationRuntime


def _build_runtime() -> ContentNormalizationRuntime:
    return ContentNormalizationRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
    )


def test_content_normalization_runtime_normalizes_headers_and_matrix() -> None:
    runtime = _build_runtime()

    headers = runtime.normalize_dataframe_headers(["  Region  ", "", "Revenue" + ("X" * 40)], max_len=10)
    rows = runtime.normalize_dataframe_matrix(
        [["  East  ", "100"], ["", ""], ["West", "Y" * 20]],
        max_cell_len=8,
    )

    assert headers == ["Region", "RevenueXXX"]
    assert rows == [["East", "100"], ["West", "YYYYYYYY"]]


def test_content_normalization_runtime_builds_table_block_dataframe_in_column_order() -> None:
    runtime = _build_runtime()

    headers, rows = runtime.table_block_to_dataframe(
        {
            "headers": ["  Region  ", "Revenue"],
            "rows": [
                {
                    "cells": [
                        {"col_index": 2, "text": "100"},
                        {"col_index": 1, "text": "East"},
                    ]
                },
                {"cells": [{"col_index": 1, "text": ""}]},
            ],
        }
    )

    assert headers == ["Region", "Revenue"]
    assert rows == [["East", "100"]]


def test_content_normalization_runtime_safe_text_list_truncates_and_filters() -> None:
    values = ContentNormalizationRuntime.safe_text_list(
        [" alpha ", "", "beta", "X" * 12],
        max_items=4,
        max_len=5,
    )

    assert values == ["alpha", "beta", "XXXXX"]


def test_content_normalization_runtime_to_float_or_none_parses_common_inputs() -> None:
    assert ContentNormalizationRuntime.to_float_or_none("1,234.5") == 1234.5
    assert ContentNormalizationRuntime.to_float_or_none(" 45% ") == 45.0
    assert ContentNormalizationRuntime.to_float_or_none(7) == 7.0
    assert ContentNormalizationRuntime.to_float_or_none("abc") is None
