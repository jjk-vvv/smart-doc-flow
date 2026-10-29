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


table_pruning_module = _load_module(
    ["app", "modules", "module2", "core", "table", "table_pruning_runtime.py"],
    "_smart_doc_flow_module2_table_pruning_runtime",
)

TablePruningRuntime = table_pruning_module.TablePruningRuntime


def _build_runtime() -> TablePruningRuntime:
    return TablePruningRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
        contains_section_marker=lambda text: "section" in str(text or "").lower() or "目录" in str(text or ""),
        header_token_is_generic=lambda text: str(text or "").strip().lower() in {"", "value", "metric", "category"},
    )


def _cell(text: str, *, numeric_value: float | None = None) -> dict[str, Any]:
    payload = {"text": text}
    if numeric_value is not None:
        payload["numeric_value"] = numeric_value
    return payload


def _row(*cells: dict[str, Any]) -> dict[str, Any]:
    return {"cells": list(cells)}


def test_table_pruning_runtime_prunes_sparse_fragments_when_robust_table_exists() -> None:
    runtime = _build_runtime()

    result = runtime.prune_fragment_tables(
        [
            {
                "table_id": "robust",
                "source": "pdf_native",
                "page": 1,
                "row_count": 3,
                "col_count": 3,
                "rows": [_row(_cell("2024"), _cell("10"), _cell("20"))],
            },
            {
                "table_id": "frag",
                "source": "pdf_native",
                "page": 1,
                "row_count": 1,
                "col_count": 1,
                "rows": [_row(_cell("7"))],
            },
        ]
    )

    assert [table["table_id"] for table in result] == ["robust"]


def test_table_pruning_runtime_keeps_only_strongest_ocr_layout_candidate_per_page() -> None:
    runtime = _build_runtime()

    result = runtime.prune_ocr_layout_density(
        [
            {
                "table_id": "ocr_weak",
                "source": "pdf_ocr_layout",
                "page": 2,
                "row_count": 5,
                "col_count": 3,
                "quality": 0.4,
                "rows": [_row(_cell("A"), _cell("B"), _cell("3", numeric_value=3.0))],
            },
            {
                "table_id": "ocr_best",
                "source": "pdf_ocr_layout",
                "page": 2,
                "row_count": 6,
                "col_count": 3,
                "quality": 0.8,
                "rows": [_row(_cell("2024", numeric_value=2024.0), _cell("10", numeric_value=10.0), _cell("30", numeric_value=30.0))],
            },
            {
                "table_id": "native_keep",
                "source": "pdf_native",
                "page": 2,
                "row_count": 2,
                "col_count": 2,
                "rows": [_row(_cell("X"), _cell("Y"))],
            },
        ]
    )

    assert [table["table_id"] for table in result] == ["native_keep", "ocr_best"]


def test_table_pruning_runtime_keeps_only_best_native_vision_table_per_page() -> None:
    runtime = _build_runtime()

    result = runtime.prune_vision_native_tables_per_page(
        [
            {
                "table_id": "native_low",
                "source": "pdf_vision_native",
                "page": 3,
                "row_count": 2,
                "col_count": 2,
                "quality": 0.5,
            },
            {
                "table_id": "native_high",
                "source": "pdf_vision_native",
                "page": 3,
                "row_count": 3,
                "col_count": 2,
                "quality": 0.9,
            },
            {
                "table_id": "other_keep",
                "source": "pdf_native",
                "page": 3,
                "row_count": 2,
                "col_count": 2,
                "quality": 0.1,
            },
        ]
    )

    assert [table["table_id"] for table in result] == ["other_keep", "native_high"]
