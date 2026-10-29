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


table_vision_payload_module = _load_module(
    ["app", "modules", "module2", "core", "table", "table_vision_payload.py"],
    "_smart_doc_flow_module2_table_vision_payload",
)

TableVisionPayloadRuntime = table_vision_payload_module.TableVisionPayloadRuntime


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


def _to_float_or_none(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vision_table_to_matrix(table_raw: Any) -> list[list[str]]:
    if not isinstance(table_raw, dict):
        return []
    return table_raw.get("matrix", [])


def _infer_headers_and_data_rows(rows_payload: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    if not rows_payload:
        return [], []

    def _row_texts(row: dict[str, Any]) -> list[str]:
        cells = sorted(row.get("cells", []), key=lambda item: int(item.get("col_index", 0) or 0))
        return [_normalize_text(str(cell.get("text", "") or "")) for cell in cells]

    headers = _row_texts(rows_payload[0])
    return headers, rows_payload[1:]


def _recover_low_signal_headers(
    headers: list[str],
    rows_payload: list[dict[str, Any]],
    *,
    caption: str = "",
    notes=None,
) -> tuple[list[str], list[dict[str, Any]]]:
    if headers == ["col_1", "col_2"]:
        return ["季度", "营收"], rows_payload
    return headers, rows_payload


def _drop_redundant_header_like_rows(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    return rows_payload


def _decorate_rows_with_meta(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for row in rows_payload:
        copied_row = dict(row)
        copied_cells: list[dict[str, Any]] = []
        for cell in row.get("cells", []):
            copied_cell = dict(cell)
            col_index = int(copied_cell.get("col_index", 0) or 0)
            copied_cell["header"] = headers[col_index - 1] if 1 <= col_index <= len(headers) else ""
            numeric_value = _to_float_or_none(copied_cell.get("text"))
            if numeric_value is not None:
                copied_cell["numeric_value"] = numeric_value
            copied_cells.append(copied_cell)
        copied_row["cells"] = copied_cells
        decorated.append(copied_row)
    return decorated


def _looks_like_false_table(headers: list[str], data_rows: list[dict[str, Any]]) -> bool:
    return headers == ["跳过", "表格"]


def _build_header_meta(headers: list[str]) -> list[dict[str, Any]]:
    return [{"name": _normalize_text(header), "col_index": idx + 1} for idx, header in enumerate(headers)]


def _build_runtime() -> TableVisionPayloadRuntime:
    return TableVisionPayloadRuntime(
        vision_max_tables_per_page=3,
        table_max_rows=6,
        table_max_cols=6,
        ocr_table_min_rows=2,
        vision_table_to_matrix=_vision_table_to_matrix,
        normalize_text=_normalize_text,
        safe_text_list=_safe_text_list,
        infer_headers_and_data_rows=_infer_headers_and_data_rows,
        recover_low_signal_headers=_recover_low_signal_headers,
        drop_redundant_header_like_rows=_drop_redundant_header_like_rows,
        decorate_rows_with_meta=_decorate_rows_with_meta,
        looks_like_false_table=_looks_like_false_table,
        build_header_meta=_build_header_meta,
        to_float_or_none=_to_float_or_none,
    )


def test_table_vision_payload_runtime_builds_tables_and_emits_refs() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    tables, next_idx = runtime.build_tables_from_vision_payload(
        payload={
            "tables": [
                {
                    "matrix": [
                        ["季度", "营收"],
                        ["Q1", "10"],
                        ["Q2", "20"],
                    ],
                    "caption": "季度营收",
                    "notes": ["单位：万元"],
                    "confidence": 0.83,
                }
            ]
        },
        page_no=2,
        table_idx=4,
        parts=parts,
        bbox_map=bbox_map,
        source_prefix="pdf_vision",
    )

    assert next_idx == 5
    assert len(tables) == 1
    assert tables[0]["table_id"] == "pdf_vision_t4"
    assert tables[0]["headers"] == ["季度", "营收"]
    assert tables[0]["row_count"] == 2
    assert tables[0]["quality"] == 0.83
    assert tables[0]["rows"][0]["cells"][1]["numeric_value"] == 10.0
    assert "pdf_vision_t4_r1_c1" in bbox_map
    assert parts


def test_table_vision_payload_runtime_skips_false_or_sparse_tables() -> None:
    runtime = _build_runtime()

    tables, next_idx = runtime.build_tables_from_vision_payload(
        payload={
            "tables": [
                {
                    "matrix": [
                        ["跳过", "表格"],
                        ["说明", "文本"],
                        ["更多", "文本"],
                    ]
                },
                {
                    "matrix": [
                        ["季度", "营收"],
                        ["Q1", "10"],
                    ]
                },
            ]
        },
        page_no=1,
        table_idx=1,
        parts=[],
        bbox_map={},
        source_prefix="pdf_vision",
    )

    assert tables == []
    assert next_idx == 3
