from __future__ import annotations

import re
from typing import Any, Callable, Dict, List


NormalizeText = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
NormalizeTokenForCompare = Callable[[str], str]
HeadersNeedRecovery = Callable[[List[str]], bool]


class TablePayloadRuntime:
    """Normalize table payloads shared by visual-first and vision flows."""

    def __init__(
        self,
        *,
        table_max_cols: int,
        table_max_rows: int,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        normalize_token_for_compare: NormalizeTokenForCompare,
        headers_need_recovery: HeadersNeedRecovery,
    ) -> None:
        self.table_max_cols = max(1, int(table_max_cols or 1))
        self.table_max_rows = max(1, int(table_max_rows or 1))
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._normalize_token_for_compare = normalize_token_for_compare
        self._headers_need_recovery = headers_need_recovery

    def extract_headers_from_table_payload(self, payload: Dict[str, Any]) -> List[str]:
        headers = self._safe_text_list(payload.get("headers"), max_items=self.table_max_cols, max_len=200)
        if headers and not self._headers_need_recovery(headers):
            return headers
        header_rows_raw = payload.get("header_rows")
        if isinstance(header_rows_raw, list):
            header_rows: List[List[str]] = []
            for row in header_rows_raw[:4]:
                if not isinstance(row, list):
                    continue
                values = [self._normalize_text(str(item or "")) for item in row[: self.table_max_cols]]
                if any(values):
                    header_rows.append(values)
            if header_rows:
                max_cols = max(len(row) for row in header_rows)
                merged: List[str] = []
                for col_idx in range(max_cols):
                    merged_parts: List[str] = []
                    seen = set()
                    for row in header_rows:
                        value = self._normalize_text(str(row[col_idx] if col_idx < len(row) else ""))
                        if not value:
                            continue
                        key = self._normalize_token_for_compare(value)
                        if key and key in seen:
                            continue
                        if key:
                            seen.add(key)
                        merged_parts.append(value)
                    merged.append(" / ".join(merged_parts))
                merged = [header for header in merged if header]
                if merged and not self._headers_need_recovery(merged):
                    return merged
                if merged:
                    headers = merged
        return headers if headers else []

    def extract_rows_from_table_payload(self, payload: Dict[str, Any]) -> List[List[str]]:
        rows_raw = payload.get("rows")
        if not isinstance(rows_raw, list):
            return []
        matrix: List[List[str]] = []
        for row in rows_raw[: self.table_max_rows]:
            values: List[str] = []
            if isinstance(row, list):
                values = [self._normalize_text(str(item or "")) for item in row[: self.table_max_cols]]
            elif isinstance(row, dict):
                row_cells = row.get("cells")
                if isinstance(row_cells, list):
                    values = [self._normalize_text(str(item or "")) for item in row_cells[: self.table_max_cols]]
                else:
                    keys = [key for key in row.keys() if str(key).lower() not in {"row_index", "id"}]
                    keys.sort()
                    values = [self._normalize_text(str(row.get(key) or "")) for key in keys[: self.table_max_cols]]
            if any(values):
                matrix.append(values)
        return matrix

    def matrix_from_html_table(self, table_html: str) -> List[List[str]]:
        html = str(table_html or "")
        if not html:
            return []
        row_chunks = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, flags=re.IGNORECASE)
        matrix: List[List[str]] = []
        for row_chunk in row_chunks[: self.table_max_rows + 1]:
            cell_chunks = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row_chunk, flags=re.IGNORECASE)
            values: List[str] = []
            for cell in cell_chunks[: self.table_max_cols]:
                text = re.sub(r"<[^>]+>", " ", str(cell or ""))
                text = self._normalize_text(text)
                values.append(text)
            if any(values):
                matrix.append(values)
        return matrix

    def vision_table_to_matrix(self, table_raw: Any) -> List[List[str]]:
        if not isinstance(table_raw, dict):
            return []

        matrix: List[List[str]] = []
        headers = self.extract_headers_from_table_payload(table_raw)
        if headers and not self._headers_need_recovery(headers):
            header_row = [self._normalize_text(str(item or "")) for item in headers[: self.table_max_cols]]
            if any(header_row):
                matrix.append(header_row)

        matrix.extend(self.extract_rows_from_table_payload(table_raw))
        return matrix
