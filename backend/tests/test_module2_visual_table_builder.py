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


visual_payload_builder_module = _load_module(
    ["module2", "app", "core", "visual", "visual_payload_builder.py"],
    "_smart_doc_flow_module2_visual_payload_builder_for_table_tests",
)

VisualTableBuilderRuntime = visual_payload_builder_module.VisualTableBuilderRuntime


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


def _append_ref(parts: list[str], bbox_map: dict[str, list[float]], ref_id: str, text: str, bbox: list[float]) -> None:
    if ref_id in bbox_map:
        return
    parts.append(f'<ref id="{ref_id}">{text}</ref>')
    bbox_map[ref_id] = bbox


def _layout_bbox_to_ref_bbox(*, page_no: int, raw_bbox: Any, page_dims: dict[int, tuple[float, float]]) -> list[float]:
    return [float(page_no), 0.1, 0.2, 0.3, 0.4]


def _build_header_meta(headers: list[str]) -> list[dict[str, Any]]:
    return [{"name": _normalize_text(header), "col_index": idx + 1} for idx, header in enumerate(headers)]


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


def _extract_headers_from_table_payload(payload: dict[str, Any]) -> list[str]:
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return []
    return [_normalize_text(str(item or "")) for item in headers if _normalize_text(str(item or ""))]


def _extract_rows_from_table_payload(payload: dict[str, Any]) -> list[list[str]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        out.append([_normalize_text(str(cell or "")) for cell in row])
    return out


def _matrix_from_html_table(table_html: str) -> list[list[str]]:
    row_chunks = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", str(table_html or ""), flags=re.IGNORECASE)
    matrix: list[list[str]] = []
    for row_chunk in row_chunks:
        cell_chunks = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row_chunk, flags=re.IGNORECASE)
        values = [_normalize_text(re.sub(r"<[^>]+>", " ", chunk)) for chunk in cell_chunks]
        values = [value for value in values if value]
        if values:
            matrix.append(values)
    return matrix


def _recover_low_signal_headers(
    headers: list[str],
    rows_payload: list[dict[str, Any]],
    *,
    caption: str = "",
    notes=None,
) -> tuple[list[str], list[dict[str, Any]]]:
    normalized = [_normalize_text(item) for item in headers]
    if normalized == ["col_1", "col_2"]:
        return ["季度", "营收"], rows_payload
    return normalized, rows_payload


def _looks_like_false_table(headers: list[str], data_rows: list[dict[str, Any]]) -> bool:
    return False


def _build_runtime(*, ocr_table_min_rows: int = 2) -> VisualTableBuilderRuntime:
    return VisualTableBuilderRuntime(
        visual_use_table_html_fallback=True,
        table_max_cols=6,
        table_max_rows=6,
        table_cell_cap=32,
        ocr_table_min_rows=ocr_table_min_rows,
        normalize_text=_normalize_text,
        safe_text_list=_safe_text_list,
        to_float_or_none=_to_float_or_none,
        append_ref=_append_ref,
        layout_bbox_to_ref_bbox=_layout_bbox_to_ref_bbox,
        build_header_meta=_build_header_meta,
        decorate_rows_with_meta=_decorate_rows_with_meta,
        extract_headers_from_table_payload=_extract_headers_from_table_payload,
        extract_rows_from_table_payload=_extract_rows_from_table_payload,
        matrix_from_html_table=_matrix_from_html_table,
        recover_low_signal_headers=_recover_low_signal_headers,
        looks_like_false_table=_looks_like_false_table,
    )


def test_visual_table_builder_runtime_builds_visual_first_table_block() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    table, emitted_cells = runtime.build_table_from_visual_payload(
        table_id="pdf_mineru_gemini_t2",
        page_no=3,
        payload={
            "title": "季度营收表",
            "headers": ["col_1", "col_2"],
            "rows": [["Q1", "10"], ["Q2", "20"]],
            "notes": ["单位：万元"],
            "confidence": 0.88,
        },
        item={
            "bbox": [10, 20, 30, 40],
            "img_path": "artifacts/table.png",
            "object_subtype": "table",
            "source_object_type": "table",
            "object_type": "table",
        },
        parts=parts,
        bbox_map=bbox_map,
        page_dims={3: (1000.0, 800.0)},
        emitted_cells=0,
        source="pdf_mineru_gemini",
    )

    assert table is not None
    assert emitted_cells == 4
    assert table["headers"] == ["季度", "营收"]
    assert table["row_count"] == 2
    assert table["col_count"] == 2
    assert table["quality"] == 0.88
    assert table["caption"] == "季度营收表"
    assert table["bbox_norm"] == [3.0, 0.1, 0.2, 0.3, 0.4]
    assert table["image_path"] == "artifacts/table.png"
    assert table["rows"][0]["cells"][0]["header"] == "季度"
    assert table["rows"][0]["cells"][1]["numeric_value"] == 10.0
    assert "pdf_mineru_gemini_t2_caption" in bbox_map
    assert "pdf_mineru_gemini_t2_note1" in bbox_map
    assert "pdf_mineru_gemini_t2_r1_c1" in bbox_map
    assert parts


def test_visual_table_builder_runtime_uses_html_fallback_when_rows_missing() -> None:
    runtime = _build_runtime(ocr_table_min_rows=1)
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    table, emitted_cells = runtime.build_table_from_visual_payload(
        table_id="pdf_mineru_gemini_t9",
        page_no=1,
        payload={},
        item={
            "caption": ["截图表格"],
            "table_body_html": "<table><tr><th>季度</th><th>营收</th></tr><tr><td>Q1</td><td>10</td></tr></table>",
            "bbox": [1, 2, 3, 4],
            "object_type": "table",
        },
        parts=parts,
        bbox_map=bbox_map,
        page_dims={1: (1000.0, 800.0)},
        emitted_cells=5,
    )

    assert table is not None
    assert emitted_cells == 7
    assert table["caption"] == "截图表格"
    assert table["headers"] == ["季度", "营收"]
    assert table["row_count"] == 1
    assert table["rows"][0]["cells"][0]["text"] == "Q1"
    assert table["rows"][0]["cells"][1]["numeric_value"] == 10.0
    assert table["source_object_type"] == "table"
    assert "pdf_mineru_gemini_t9_caption" in bbox_map
