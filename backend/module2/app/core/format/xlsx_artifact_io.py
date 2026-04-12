from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..table.table_metadata import build_header_meta


MODULE2_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE2_ROOT.parents[1]


def _runtime_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT


def _data_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    runtime_root = _runtime_root_dir()
    runtime_data_dir = (runtime_root / "runtime-data").resolve()
    if runtime_data_dir.exists():
        return runtime_data_dir
    return runtime_root


def _resolve_module2_path(raw_value: str, default_path: Path) -> Path:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_path.resolve()
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()

    candidate_module2 = (MODULE2_ROOT / path).resolve()
    candidate_repo = (REPO_ROOT / path).resolve()
    normalized = raw.replace("\\", "/").lower()
    if normalized.startswith("backend/module2/"):
        return candidate_repo
    if candidate_repo.exists() and not candidate_module2.exists():
        return candidate_repo
    return candidate_module2


def resolve_module2_artifact_root_dir() -> Path:
    configured = str(os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "") or "").strip()
    root = _resolve_module2_path(configured, _data_root_dir() / "module2" / "artifacts")
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_artifact_json_path(path_value: Any) -> Optional[Path]:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    direct_candidate = Path(raw)
    if direct_candidate.is_absolute():
        try:
            return direct_candidate.resolve()
        except Exception:
            return None

    normalized = raw.replace("\\", "/").strip().lstrip("/")
    artifact_root = resolve_module2_artifact_root_dir()
    candidates = [
        (artifact_root / normalized).resolve(),
        (_data_root_dir() / normalized).resolve(),
        (_runtime_root_dir() / normalized).resolve(),
        (REPO_ROOT / normalized).resolve(),
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


@lru_cache(maxsize=256)
def _read_json_cached(path_str: str) -> Dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _inflate_compact_xlsx_rows_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = str(payload.get("version") or "").strip().lower()
    rows = payload.get("rows")
    if version != "module2-xlsx-sheet-rows-v2" or not isinstance(rows, list):
        return payload if isinstance(payload, dict) else {}

    headers = list(payload.get("headers") or [])
    inflated_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            continue
        try:
            row_index = int(row[0] or 0)
        except Exception:
            row_index = 0
        try:
            source_row_index = int(row[1] or row_index)
        except Exception:
            source_row_index = row_index
        cells_blob = row[2]
        if not isinstance(cells_blob, list):
            continue
        inflated_cells: List[Dict[str, Any]] = []
        for cell in cells_blob:
            if not isinstance(cell, list) or len(cell) < 4:
                continue
            try:
                col_index = int(cell[0] or 0)
            except Exception:
                col_index = 0
            if col_index <= 0:
                continue
            text = str(cell[1] or "")
            if not text:
                continue
            ref_id = str(cell[2] or "")
            bbox = list(cell[3][:5]) if isinstance(cell[3], list) else []
            inflated_cell: Dict[str, Any] = {
                "col_index": col_index,
                "text": text,
                "ref_id": ref_id,
                "bbox": bbox,
                "header": str(headers[col_index - 1] or f"col_{col_index}") if col_index <= len(headers) else f"col_{col_index}",
            }
            if len(cell) >= 5 and cell[4] is not None:
                inflated_cell["numeric_value"] = cell[4]
            inflated_cells.append(inflated_cell)
        if inflated_cells:
            inflated_rows.append(
                {
                    "row_index": row_index,
                    "source_row_index": source_row_index,
                    "cells": inflated_cells,
                }
            )

    inflated_payload = dict(payload)
    inflated_payload["rows"] = inflated_rows
    if "header_meta" not in inflated_payload:
        inflated_payload["header_meta"] = build_header_meta(headers)
    return inflated_payload


@lru_cache(maxsize=256)
def _load_xlsx_sheet_rows_payload_cached(path_str: str) -> Dict[str, Any]:
    payload = _read_json_cached(path_str)
    if not isinstance(payload, dict):
        return {}
    return _inflate_compact_xlsx_rows_payload(payload)


def load_xlsx_workbook_manifest(manifest_path: Any) -> Dict[str, Any]:
    resolved = resolve_artifact_json_path(manifest_path)
    if resolved is None:
        return {}
    try:
        payload = _read_json_cached(str(resolved))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_xlsx_sheet_rows_artifact(rows_path: Any) -> Dict[str, Any]:
    resolved = resolve_artifact_json_path(rows_path)
    if resolved is None:
        return {}
    try:
        payload = _load_xlsx_sheet_rows_payload_cached(str(resolved))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_xlsx_sheet_payload_for_table(table: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(table, dict):
        return {}
    rows_path = str(table.get("xlsx_sheet_rows_artifact_path") or "").strip()
    if rows_path:
        payload = load_xlsx_sheet_rows_artifact(rows_path)
        if payload:
            return payload

    manifest_path = str(table.get("xlsx_workbook_manifest_path") or "").strip()
    sheet_index = int(table.get("sheet_index", 0) or 0)
    if not manifest_path or sheet_index <= 0:
        return {}
    manifest = load_xlsx_workbook_manifest(manifest_path)
    for item in manifest.get("sheets", []) or []:
        if int((item or {}).get("sheet_index", 0) or 0) != sheet_index:
            continue
        candidate_path = str((item or {}).get("rows_artifact_path") or "").strip()
        if not candidate_path:
            continue
        payload = load_xlsx_sheet_rows_artifact(candidate_path)
        if payload:
            return payload
    return {}


def load_xlsx_sheet_rows_for_table(table: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = load_xlsx_sheet_payload_for_table(table)
    rows = payload.get("rows") if isinstance(payload, dict) else []
    return list(rows or []) if isinstance(rows, list) else []
