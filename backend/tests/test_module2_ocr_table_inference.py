from __future__ import annotations

import importlib.util
import re
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


ocr_table_utils_module = _load_module(
    ["app", "modules", "module2", "core", "table", "ocr_table_utils.py"],
    "_smart_doc_flow_module2_ocr_table_utils_for_inference",
)
ocr_table_inference_module = _load_module(
    ["app", "modules", "module2", "core", "table", "ocr_table_inference.py"],
    "_smart_doc_flow_module2_ocr_table_inference",
)

OcrTableUtils = ocr_table_utils_module.OcrTableUtils
OcrTableInferenceRuntime = ocr_table_inference_module.OcrTableInferenceRuntime


def _build_utils():
    return OcrTableUtils(
        ocr_max_pages=4,
        ocr_front_scan_pages=6,
        ocr_extra_sample_pages=2,
        ocr_cue_neighbor=1,
        ocr_cue_max_pages=8,
        ocr_max_scan_pages=10,
        ocr_cue_boost_max_pages=8,
        ocr_min_coverage_ratio=0.2,
        ocr_min_scan_pages=4,
        visual_weak_table_min=4,
        ocr_table_min_quality=0.52,
        ocr_line_aug_max_extra_cue_pages=3,
        ocr_uncovered_line_aug_pages=4,
        table_merge_enable=True,
        ocr_table_min_rows=2,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        looks_like_table_cue_text=lambda text: ("表" in text) or ("table" in str(text).lower()),
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
    )


def _infer_headers_and_data_rows(rows_payload: list[dict]) -> tuple[list[str], list[dict]]:
    if not rows_payload:
        return [], []
    header_row = rows_payload[0]
    headers = [str(cell.get("text", "")) for cell in sorted(header_row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))]
    data_rows: list[dict] = []
    for idx, row in enumerate(rows_payload[1:], start=1):
        data_rows.append({"row_index": idx, "cells": list(row.get("cells", []))})
    return headers, data_rows


def _decorate_rows_with_meta(rows_payload: list[dict], headers: list[str]) -> list[dict]:
    header_map = {idx: header for idx, header in enumerate(headers, start=1)}
    decorated: list[dict] = []
    for row_idx, row in enumerate(rows_payload, start=1):
        cells_payload = []
        for cell in row.get("cells", []):
            text = str(cell.get("text", "")).strip()
            numeric_value = float(text) if re.fullmatch(r"-?\d+(?:\.\d+)?", text) else None
            cells_payload.append(
                {
                    **cell,
                    "text": text,
                    "header": header_map.get(int(cell.get("col_index", 0) or 0), ""),
                    "numeric_value": numeric_value,
                }
            )
        if cells_payload:
            decorated.append({"row_index": row_idx, "cells": cells_payload})
    return decorated


def _build_header_meta(headers: list[str]) -> list[dict]:
    return [{"col_index": idx, "raw": header, "name": header, "name_norm": header.lower(), "unit": None} for idx, header in enumerate(headers, start=1)]


def _build_runtime():
    utils = _build_utils()
    return OcrTableInferenceRuntime(
        ocr_table_min_quality=0.52,
        ocr_table_min_cols=2,
        ocr_table_min_rows=2,
        ocr_table_row_tol=0.018,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        ocr_table_relaxed_row_gap_scale=1.5,
        ocr_table_relaxed_align_min=0.36,
        ocr_table_relaxed_overlap_min=0.3,
        ocr_table_relaxed_col_diff_max=2,
        table_max_rows=20,
        table_max_cols=8,
        table_cell_cap=200,
        table_merge_enable=True,
        runtime_page_count_provider=lambda: 20,
        infer_headers_and_data_rows=_infer_headers_and_data_rows,
        drop_redundant_header_like_rows=lambda rows, headers: rows,
        decorate_rows_with_meta=_decorate_rows_with_meta,
        build_header_meta=_build_header_meta,
        looks_like_false_table=lambda headers, data_rows: False,
        normalize_text=lambda text: str(text or "").strip(),
        contains_section_marker=lambda text: "章" in str(text or ""),
        is_page_number_token=lambda text: bool(re.fullmatch(r"\d{1,4}", str(text or "").strip())),
        dedupe_ocr_cells=utils.dedupe_ocr_cells,
        median_cell_height=utils.median_cell_height,
        cluster_ocr_rows=utils.cluster_ocr_rows,
        group_table_rows=utils.group_table_rows,
        split_group_by_row_gaps=utils.split_group_by_row_gaps,
        build_col_anchors=utils.build_col_anchors,
        nearest_anchor_index=utils.nearest_anchor_index,
        expand_group_with_sparse_rows=utils.expand_group_with_sparse_rows,
        table_quality_score=utils.table_quality_score,
        split_table_line=utils.split_table_line,
        is_table_line=utils.is_table_line,
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
    )


def test_ocr_table_inference_runtime_builds_tables_from_page_lines() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    tables = runtime.infer_tables_from_page_lines(
        {
            1: [
                "年份    温度    压力",
                "2024    25    13",
                "2025    27    14",
            ]
        },
        parts,
        bbox_map,
        "line",
    )

    assert len(tables) == 1
    assert tables[0]["headers"] == ["年份", "温度", "压力"]
    assert tables[0]["row_count"] == 2
    assert 'ref id="line_t1_r1_c1"' in "".join(parts)
    assert "line_t1_r1_c1" in bbox_map


def test_ocr_table_inference_runtime_builds_tables_from_ocr_cells() -> None:
    runtime = _build_runtime()
    page_cells = {
        1: [
            {"text": "年份", "x_center": 0.2, "y_center": 0.1, "bbox": [1.0, 0.1, 0.0, 0.1, 0.02]},
            {"text": "温度", "x_center": 0.5, "y_center": 0.1, "bbox": [1.0, 0.4, 0.0, 0.1, 0.02]},
            {"text": "压力", "x_center": 0.8, "y_center": 0.1, "bbox": [1.0, 0.7, 0.0, 0.1, 0.02]},
            {"text": "2024", "x_center": 0.2, "y_center": 0.2, "bbox": [1.0, 0.1, 0.1, 0.1, 0.02]},
            {"text": "25", "x_center": 0.5, "y_center": 0.2, "bbox": [1.0, 0.4, 0.1, 0.1, 0.02]},
            {"text": "13", "x_center": 0.8, "y_center": 0.2, "bbox": [1.0, 0.7, 0.1, 0.1, 0.02]},
            {"text": "2025", "x_center": 0.2, "y_center": 0.3, "bbox": [1.0, 0.1, 0.2, 0.1, 0.02]},
            {"text": "27", "x_center": 0.5, "y_center": 0.3, "bbox": [1.0, 0.4, 0.2, 0.1, 0.02]},
            {"text": "14", "x_center": 0.8, "y_center": 0.3, "bbox": [1.0, 0.7, 0.2, 0.1, 0.02]},
        ]
    }

    tables = runtime.infer_tables_from_ocr_cells(page_cells)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["年份", "温度", "压力"]
    assert tables[0]["row_count"] == 2
    assert tables[0]["col_count"] == 3
    assert tables[0]["quality"] >= 0.52
