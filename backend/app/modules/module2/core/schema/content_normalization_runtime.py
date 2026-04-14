from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple


NormalizeText = Callable[[str], str]


class ContentNormalizationRuntime:
    """Shared pure helpers for normalizing dataframe-like and list-like payloads."""

    def __init__(self, *, normalize_text: NormalizeText) -> None:
        self._normalize_text = normalize_text

    def table_block_to_dataframe(self, table: Dict[str, Any]) -> Tuple[List[str], List[List[str]]]:
        headers = [
            self._normalize_text(str(item or ""))
            for item in (table.get("headers") if isinstance(table.get("headers"), list) else [])
        ]
        headers = [item for item in headers if item]
        rows_out: List[List[str]] = []
        for row in table.get("rows") if isinstance(table.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            cells = row.get("cells") if isinstance(row.get("cells"), list) else []
            ordered = sorted(
                [cell for cell in cells if isinstance(cell, dict)],
                key=lambda item: int(item.get("col_index", 0) or 0),
            )
            values = [self._normalize_text(str(cell.get("text", "") or "")) for cell in ordered]
            if any(values):
                rows_out.append(values)
        return headers, rows_out

    def normalize_dataframe_headers(self, headers: Any, *, max_len: int = 120) -> List[str]:
        if not isinstance(headers, list):
            return []
        out: List[str] = []
        for item in headers:
            text = self._normalize_text(str(item or ""))
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    def normalize_dataframe_matrix(self, rows: Any, *, max_cell_len: int = 160) -> List[List[str]]:
        if not isinstance(rows, list):
            return []
        out: List[List[str]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            values: List[str] = []
            for cell in row:
                text = self._normalize_text(str(cell or ""))
                if len(text) > max_cell_len:
                    text = text[:max_cell_len]
                values.append(text)
            if any(values):
                out.append(values)
        return out

    @staticmethod
    def safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values[:max_items]:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    @staticmethod
    def to_float_or_none(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            cleaned = re.sub(r"[,\s%\uFF05]", "", cleaned)
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
