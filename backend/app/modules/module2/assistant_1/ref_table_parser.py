from __future__ import annotations

import html
import re
from typing import Any


_REF_TAG_RE = re.compile(r'<ref\s+id="(?P<id>[^"]+)">(?P<value>.*?)</ref>', re.IGNORECASE | re.DOTALL)
_CELL_ID_RE = re.compile(r"(?P<table_id>.+?)_r(?P<row>\d+)_c(?P<col>\d+)$", re.IGNORECASE)


def _clean_value(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(part for part in text.split())


def _trim_text(value: Any, limit: int = 80) -> str:
    text = _clean_value(str(value or ""))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def parse_ref_rows(text: str, *, max_rows: int = 12, max_cells_per_row: int = 24) -> dict[str, Any]:
    rows: dict[tuple[str, int], list[dict[str, Any]]] = {}
    table_ids: list[str] = []

    for match in _REF_TAG_RE.finditer(str(text or "")):
        raw_id = str(match.group("id") or "").strip()
        cell_match = _CELL_ID_RE.match(raw_id)
        if not cell_match:
            continue
        table_id = str(cell_match.group("table_id") or "").strip()
        row_index = int(cell_match.group("row") or 0)
        col_index = int(cell_match.group("col") or 0)
        if not table_id or row_index <= 0 or col_index <= 0:
            continue
        if table_id not in table_ids:
            table_ids.append(table_id)
        key = (table_id, row_index)
        rows.setdefault(key, []).append(
            {
                "col_index": col_index,
                "value": _trim_text(match.group("value"), 120),
            }
        )

    if not rows:
        return {}

    ordered_rows: list[dict[str, Any]] = []
    for (table_id, row_index), cells in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1])):
        ordered_rows.append(
            {
                "table_id": table_id,
                "row_index": row_index,
                "cells": sorted(cells, key=lambda item: int(item.get("col_index") or 0))[:max_cells_per_row],
            }
        )

    header_rows = [row for row in ordered_rows if int(row.get("row_index") or 0) == 1][:1]
    return {
        "table_ids": table_ids[:4],
        "row_count": len(ordered_rows),
        "header_rows": header_rows,
        "rows": ordered_rows[:max_rows],
    }


def build_ref_focus_preview(
    text: str,
    *,
    entity_hints: list[str] | tuple[str, ...] = (),
    date_hints: list[str] | tuple[str, ...] = (),
    metric_hints: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    parsed = parse_ref_rows(text)
    if not parsed:
        return {}

    normalized_entities = [str(item or "").strip().lower() for item in entity_hints if str(item or "").strip()]
    normalized_dates = [str(item or "").strip().lower() for item in date_hints if str(item or "").strip()]
    normalized_metrics = [str(item or "").strip().lower() for item in metric_hints if str(item or "").strip()]

    focused_rows: list[dict[str, Any]] = []
    matched_row_indices: list[int] = []

    for row in parsed.get("rows", []):
        if not isinstance(row, dict):
            continue
        cell_values = [str(cell.get("value") or "") for cell in row.get("cells", []) if isinstance(cell, dict)]
        row_text = " ".join(cell_values).lower()
        score = 0
        reasons: list[str] = []

        if normalized_entities and any(entity in row_text for entity in normalized_entities):
            score += 2
            reasons.append("entity")
        if normalized_dates and any(date in row_text for date in normalized_dates):
            score += 3
            reasons.append("date")
        if normalized_metrics and any(metric in row_text for metric in normalized_metrics):
            score += 1
            reasons.append("metric")

        if score <= 0:
            continue

        row_index = int(row.get("row_index") or 0)
        if row_index > 0:
            matched_row_indices.append(row_index)
        focused_rows.append(
            {
                "table_id": str(row.get("table_id") or ""),
                "row_index": row_index,
                "match_score": score,
                "match_reasons": reasons,
                "cells": row.get("cells", []),
            }
        )

    focused_rows.sort(key=lambda item: (-int(item.get("match_score") or 0), int(item.get("row_index") or 0)))

    return {
        "table_ids": parsed.get("table_ids", []),
        "row_count": int(parsed.get("row_count") or 0),
        "header_rows": parsed.get("header_rows", []),
        "focused_rows": focused_rows[:3],
        "matched_row_indices": sorted(set(matched_row_indices))[:6],
    }
