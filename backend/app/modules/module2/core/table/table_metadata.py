from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Tuple

try:
    from app.modules.module2.core.format.plain_text_parser import normalize_text
except ModuleNotFoundError:
    def normalize_text(text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def normalize_token_for_compare(text: str) -> str:
    token = str(text or "").strip().lower()
    token = re.sub(r"[\s\(\)\[\]{}<>/\\,.;:：，、\-_]+", "", token)
    return token


def normalize_token_for_compare_legacy(text: str) -> str:
    """Compatibility alias retained for migrated call sites."""
    return normalize_token_for_compare(text)


def extract_header_name_and_unit(raw_header: str) -> Tuple[str, str | None]:
    text = normalize_text(str(raw_header or ""))
    if not text:
        return "", None
    match = re.match(r"^(.*?)\s*[\(\[（【]\s*([^\)\]）】]{1,24})\s*[\)\]）】]\s*$", text)
    if match:
        name = normalize_text(match.group(1))
        unit = normalize_text(match.group(2))
        return name or text, unit or None

    match2 = re.match(r"^(.*?)\s*[/／]\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc0-9\-]{1,16})$", text)
    if match2:
        name = normalize_text(match2.group(1))
        unit = normalize_text(match2.group(2))
        return name or text, unit or None
    return text, None


def extract_header_name_and_unit_legacy(raw_header: str) -> Tuple[str, str | None]:
    """Compatibility alias retained for migrated call sites."""
    return extract_header_name_and_unit(raw_header)


def extract_number_meta(text: str, unit_hint: str | None) -> Dict[str, Any]:
    raw = normalize_text(str(text or ""))
    result: Dict[str, Any] = {
        "value_type": "text",
        "numeric_value": None,
        "ratio_value": None,
        "detected_unit": unit_hint,
        "normalized_text": raw,
    }
    if not raw:
        return result

    cleaned = re.sub(r"[,\uFF0C\s]", "", raw)
    numeric_matches = list(re.finditer(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned))
    if len(numeric_matches) > 1:
        return result

    sci_text = cleaned.replace("×", "x").replace("X", "x").replace("＊", "x").replace("−", "-")
    sci_match = re.search(r"([-+]?\d*\.?\d+)\s*[x*]\s*10(?:\^)?\s*([-+]?\d+)", sci_text)
    if sci_match:
        try:
            base = float(sci_match.group(1))
            exponent = int(sci_match.group(2))
            if exponent > 308 or exponent < -308:
                return result
            value = base * (10.0 ** exponent)
        except (ValueError, OverflowError):
            return result
        number_match = None
    else:
        number_match = numeric_matches[0] if numeric_matches else None
        if not number_match:
            return result
        try:
            value = float(number_match.group(0))
        except (ValueError, OverflowError):
            return result

    suffix = cleaned[number_match.end() :] if not sci_match and number_match else ""
    scale = 1.0
    if suffix.startswith("\u4ebf"):
        scale *= 1e8
    elif suffix.startswith("\u4e07"):
        scale *= 1e4
    elif suffix.startswith("\u5343"):
        scale *= 1e3
    elif suffix.startswith("\u767e"):
        scale *= 1e2

    try:
        numeric_value = value * scale
    except OverflowError:
        return result
    if not math.isfinite(numeric_value):
        return result

    detected_unit = unit_hint
    if "%" in raw or "\uff05" in raw:
        detected_unit = detected_unit or "%"
        ratio = numeric_value / 100.0
    else:
        ratio = None
    if ratio is not None and not math.isfinite(ratio):
        ratio = None

    unit_match = re.search(
        r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc/\-]+)$",
        raw,
    )
    if unit_match:
        detected_unit = unit_match.group(1)

    result.update(
        {
            "value_type": "number",
            "numeric_value": round(numeric_value, 10),
            "ratio_value": None if ratio is None else round(ratio, 10),
            "detected_unit": detected_unit,
            "normalized_text": str(round(numeric_value, 10)),
        }
    )
    return result


def build_header_meta(headers: List[str]) -> List[Dict[str, Any]]:
    meta: List[Dict[str, Any]] = []
    for idx, raw in enumerate(headers, start=1):
        name, unit = extract_header_name_and_unit(raw)
        meta.append(
            {
                "col_index": idx,
                "raw": raw,
                "name": name,
                "name_norm": normalize_token_for_compare(name),
                "unit": unit,
            }
        )
    return meta


def decorate_rows_with_meta(rows_payload: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
    header_meta = build_header_meta(headers)
    header_map = {int(item.get("col_index", 0)): item for item in header_meta}
    decorated: List[Dict[str, Any]] = []
    row_idx = 1
    for row in rows_payload:
        cells = sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
        out_cells: List[Dict[str, Any]] = []
        for cell in cells:
            col_idx = int(cell.get("col_index", 0) or 0)
            text = normalize_text(str(cell.get("text", "")))
            if not text:
                continue
            header = header_map.get(col_idx, {"name": f"col_{col_idx}", "name_norm": "", "unit": None})
            number_meta = extract_number_meta(text, header.get("unit"))
            out = dict(cell)
            out.update(
                {
                    "text": text,
                    "header": header.get("name"),
                    "header_norm": header.get("name_norm"),
                    "header_unit": header.get("unit"),
                    "value_type": number_meta.get("value_type"),
                    "numeric_value": number_meta.get("numeric_value"),
                    "ratio_value": number_meta.get("ratio_value"),
                    "detected_unit": number_meta.get("detected_unit"),
                    "normalized_text": number_meta.get("normalized_text"),
                }
            )
            out_cells.append(out)
        if out_cells:
            source_row_index = int(row.get("row_index", row_idx) or row_idx)
            decorated.append(
                {
                    "row_index": row_idx,
                    "source_row_index": source_row_index,
                    "cells": out_cells,
                }
            )
            row_idx += 1
    return decorated
