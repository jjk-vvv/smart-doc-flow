from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple


NormalizeText = Callable[[str], str]
NormalizeTokenForCompare = Callable[[str], str]
TextPredicate = Callable[[str], bool]
RuntimePageCountProvider = Callable[[], int]


class TableHeaderRuntime:
    """Infer and repair table headers while preserving parser-compatible method contracts."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        normalize_token_for_compare: NormalizeTokenForCompare,
        contains_figure_marker: TextPredicate,
        contains_catalog_marker: TextPredicate,
        runtime_page_count_provider: RuntimePageCountProvider,
    ) -> None:
        self._normalize_text = normalize_text
        self._normalize_token_for_compare = normalize_token_for_compare
        self._contains_figure_marker = contains_figure_marker
        self._contains_catalog_marker = contains_catalog_marker
        self._runtime_page_count_provider = runtime_page_count_provider

    @staticmethod
    def is_unit_like_token(text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        value = value.strip("()[]{}<>（）【】")
        if not value:
            return False
        unit_set = {
            "%", "\uff05", "\u2030",
            "\u2103", "\u00b0c", "\u2109", "\u00b0f",
            "k", "pa", "kpa", "mpa", "bar",
            "s", "sec", "min", "h",
            "g", "kg", "mg", "ug", "\u03bcg",
            "l", "ml", "m3", "m3/h", "l/h",
            "mol", "mol/l", "g/l", "mg/l", "kg/m3",
            "wt%", "vol%", "ppm", "ppb", "ph",
        }
        if value in unit_set:
            return True
        return bool(re.fullmatch(r"[a-z%\u00b0\u2103\u2109\u2030\u03bc/\-0-9]{1,16}", value))

    @staticmethod
    def header_token_is_generic(text: str) -> bool:
        probe = str(text or "").strip().lower()
        if not probe:
            return True
        compact = re.sub(r"[\s_\-/:|]+", "", probe)
        if bool(re.fullmatch(r"col\d{1,3}", compact)):
            return True
        if bool(re.fullmatch(r"[\?？�_\-—–~·\.]{1,24}", probe)):
            return True
        if bool(re.fullmatch(r"(?:value|metric|category|item|desc|description)[_\s\-]?\d{0,2}", compact)):
            return True
        if bool(re.fullmatch(r"(?:数值|类别|项目|说明|指标)[_\s\-]?\d{0,2}", str(text or "").strip())):
            return True
        if compact in {"na", "n/a", "null", "none", "unknown", "unk", "待定", "未知", "未识别"}:
            return True
        meaningful = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", compact)
        return not bool(meaningful)

    @staticmethod
    def cell_text_numeric_like(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"[\s,\uFF0C]", "", value)
        if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?[%％]?", compact):
            return True
        if re.fullmatch(r"(?:19|20)\d{2}年?", compact):
            return True
        return bool(re.search(r"\d", compact))

    @staticmethod
    def temporal_text_like(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        compact = re.sub(r"[\s,\uFF0C]", "", value)
        temporal_patterns = (
            r"(?:19|20)\d{2}(?:\u5e74|[?])?",
            r"(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}(?:日)?)?[?]?",
            r"\d{1,2}(?:[-~\u81f3]\d{1,2})?(?:\u6708|[?])",
            r"(?:Q[1-4]|[1-4]Q|H[12])",
            r"(?:[1-4]\u5b63\u5ea6|\u7b2c[\u4e00\u4e8c\u4e09\u56db]\u5b63\u5ea6)",
            r"(?:\u4e0a\u534a\u5e74|\u4e0b\u534a\u5e74)",
        )
        return any(re.fullmatch(pattern, compact, flags=re.IGNORECASE) for pattern in temporal_patterns)

    @staticmethod
    def header_text_has_label_cue(text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        compact = re.sub(r"[\s_\-/:|()（）\[\]{}]+", "", value)
        if re.search(r"(?:name|metric|item|category|region|date|time|year|unit|desc|description|index|label)", compact):
            return True
        label_cues = (
            "\u540d\u79f0",
            "\u6307\u6807",
            "\u9879\u76ee",
            "\u7c7b\u522b",
            "\u5730\u533a",
            "\u65e5\u671f",
            "\u65f6\u95f4",
            "\u5e74\u4efd",
            "\u5355\u4f4d",
            "\u8bf4\u660e",
            "\u79d1\u76ee",
            "\u5185\u5bb9",
            "\u5e8f\u53f7",
        )
        return any(token in compact for token in label_cues)

    @staticmethod
    def merge_header_rows(row1: List[str], row2: List[str], col_count: int) -> List[str]:
        merged: List[str] = []
        for idx in range(col_count):
            left = row1[idx] if idx < len(row1) else ""
            right = row2[idx] if idx < len(row2) else ""
            if left and right:
                merged.append(f"{left} ({right})")
            elif left:
                merged.append(left)
            elif right:
                merged.append(right)
            else:
                merged.append("")
        return merged

    def headers_need_recovery(self, headers: List[str]) -> bool:
        normalized = [self._normalize_text(str(item or "")) for item in headers]
        normalized = [item for item in normalized if item]
        if not normalized:
            return True
        generic_count = sum(1 for item in normalized if self.header_token_is_generic(item))
        data_value_like_count = sum(
            1
            for item in normalized
            if self.cell_text_numeric_like(item)
            and not self.temporal_text_like(item)
        )
        data_value_ratio = data_value_like_count / float(max(len(normalized), 1))
        _numeric_like_count = sum(1 for item in normalized if self.cell_text_numeric_like(item))
        _temporal_like_count = sum(
            1
            for item in normalized
            if re.fullmatch(r"(?:19|20)\d{2}年?", item)
            or re.fullmatch(r"(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", item)
        )
        if generic_count <= 0:
            return data_value_ratio >= 0.4
        meaningful_count = len(normalized) - generic_count
        if meaningful_count <= 0:
            return True
        if generic_count / float(max(len(normalized), 1)) >= 0.5:
            return True
        return data_value_ratio >= 0.4

    def row_payload_texts(self, row: Dict[str, Any], col_count: int) -> List[str]:
        cells = sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
        cell_map: Dict[int, str] = {}
        for cell in cells:
            col_index = int(cell.get("col_index", 0) or 0)
            if col_index <= 0:
                continue
            cell_map[col_index] = self._normalize_text(str(cell.get("text", "") or ""))
        return [cell_map.get(idx, "") for idx in range(1, max(col_count, 0) + 1)]

    def column_numeric_ratio(self, values: List[str], *, ignore_temporal: bool = False) -> float:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return 0.0
        numeric_hits = 0
        for value in non_empty:
            if not self.cell_text_numeric_like(value):
                continue
            if ignore_temporal and self.temporal_text_like(value):
                continue
            numeric_hits += 1
        return numeric_hits / float(len(non_empty))

    def column_percent_ratio(self, values: List[str]) -> float:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return 0.0
        hits = sum(1 for value in non_empty if "%" in value or "％" in value or "占比" in value)
        return hits / float(len(non_empty))

    def column_year_ratio(self, values: List[str]) -> float:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return 0.0
        hits = sum(1 for value in non_empty if re.fullmatch(r"(?:19|20)\d{2}年?", value))
        return hits / float(len(non_empty))

    def column_date_ratio(self, values: List[str]) -> float:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return 0.0
        hits = sum(
            1
            for value in non_empty
            if re.fullmatch(r"(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", value)
        )
        return hits / float(len(non_empty))

    def column_geo_ratio(self, values: List[str]) -> float:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return 0.0
        geo_tokens = (
            "省",
            "市",
            "区",
            "县",
            "乡",
            "镇",
            "村",
            "全国",
            "全省",
            "全市",
            "城区",
            "农村",
            "城市",
            "地区",
        )
        hits = sum(1 for value in non_empty if any(token in value for token in geo_tokens))
        return hits / float(len(non_empty))

    def figure_axis_dimension_label(self, values: List[str], *, fallback: str = "类别") -> str:
        normalized = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not normalized:
            return fallback
        if self.column_year_ratio(normalized) >= 0.6:
            return "年份"
        if self.column_date_ratio(normalized) >= 0.6:
            return "日期"
        if self.column_geo_ratio(normalized) >= 0.6:
            return "地区"
        return fallback

    def caption_metric_hint(self, caption: str, notes: Optional[List[str]] = None) -> str:
        text = self._normalize_text(" ".join([caption] + [str(item or "") for item in (notes or [])]))
        if not text:
            return ""
        text = re.sub(r"^(?:表|图)\s*[0-9A-Za-z一二三四五六七八九十.\-]+", "", text)
        text = re.sub(r"[（(][^()（）]{0,24}[)）]", "", text)
        text = re.sub(
            r"(?:统计表|统计图|汇总表|情况表|情况图|趋势图|分布图|结构图|对比图|示意图|统计情况|统计|情况|汇总|变化趋势|变化|趋势|分布|构成|明细|一览表)$",
            "",
            text,
        )
        text = self._normalize_text(text)
        if len(text) > 16:
            text = text[:16].rstrip("、，,;；:： ")
        return text

    def should_promote_first_data_row_to_header(self, row1: List[str], row2: List[str], col_count: int) -> bool:
        values1 = [self._normalize_text(value) for value in row1 if self._normalize_text(value)]
        values2 = [self._normalize_text(value) for value in row2 if self._normalize_text(value)]
        if not values1 or not values2:
            return False
        if self.is_caption_like_header_row(row1, col_count):
            return False
        if not self.looks_like_header_row(row1):
            return False
        numeric_ratio1 = self.column_numeric_ratio(values1, ignore_temporal=True)
        numeric_ratio2 = self.column_numeric_ratio(values2, ignore_temporal=True)
        if numeric_ratio1 > 0.34:
            return False
        return numeric_ratio2 >= 0.45 and numeric_ratio2 >= (numeric_ratio1 + 0.2)

    def guess_header_from_column_values(
        self,
        *,
        col_index: int,
        values: List[str],
        numeric_rank: int,
        numeric_col_count: int,
        caption_hint: str,
    ) -> str:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return f"col_{col_index + 1}"
        if self.column_year_ratio(non_empty) >= 0.6:
            return "年份"
        if self.column_date_ratio(non_empty) >= 0.6:
            return "日期"
        if self.column_percent_ratio(non_empty) >= 0.5:
            return "占比"
        if self.column_geo_ratio(non_empty) >= 0.6:
            return "地区"

        numeric_ratio = self.column_numeric_ratio(non_empty)
        if numeric_ratio <= 0.25:
            avg_len = sum(len(item) for item in non_empty) / float(max(len(non_empty), 1))
            if avg_len >= 10 and col_index > 0:
                return "说明"
            if col_index == 0:
                return "类别"
            return f"类别_{col_index + 1}"

        if caption_hint and numeric_col_count <= 1:
            return caption_hint
        if caption_hint and numeric_rank > 0 and numeric_col_count > 1 and numeric_rank <= 2:
            return f"{caption_hint}_{numeric_rank}"
        if numeric_col_count <= 1:
            return "数值"
        return f"数值_{max(1, numeric_rank)}"

    def recover_low_signal_headers(
        self,
        headers: List[str],
        rows_payload: List[Dict[str, Any]],
        *,
        caption: str = "",
        notes: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        col_count = max(
            len(headers),
            max((len(row.get("cells", [])) for row in rows_payload), default=0),
        )
        if col_count <= 0:
            return headers, rows_payload

        normalized_headers = [self._normalize_text(str(item or "")) for item in headers[:col_count]]
        if len(normalized_headers) < col_count:
            normalized_headers.extend([""] * (col_count - len(normalized_headers)))

        repaired_rows = list(rows_payload)
        promoted_header_row = False
        needs_recovery = self.headers_need_recovery(normalized_headers)
        if needs_recovery and len(repaired_rows) >= 2:
            row1 = self.row_payload_texts(repaired_rows[0], col_count)
            row2 = self.row_payload_texts(repaired_rows[1], col_count)
            if self.should_promote_first_data_row_to_header(row1, row2, col_count):
                normalized_headers = row1[:]
                repaired_rows = repaired_rows[1:]
                promoted_header_row = True
                needs_recovery = self.headers_need_recovery(normalized_headers)

        caption_hint = self.caption_metric_hint(caption, notes=notes)
        column_values: List[List[str]] = []
        for col_idx in range(1, col_count + 1):
            values: List[str] = []
            for row in repaired_rows[:8]:
                row_values = self.row_payload_texts(row, col_count)
                value = row_values[col_idx - 1] if (col_idx - 1) < len(row_values) else ""
                if value:
                    values.append(value)
            column_values.append(values)

        numeric_positions = [
            idx
            for idx, values in enumerate(column_values)
            if self.column_numeric_ratio(values, ignore_temporal=True) >= 0.5
        ]
        numeric_rank_map = {idx: rank for rank, idx in enumerate(numeric_positions, start=1)}

        repaired_headers: List[str] = []
        for idx in range(col_count):
            current = normalized_headers[idx] if idx < len(normalized_headers) else ""
            preserve_current = bool(current) and (promoted_header_row or not self.header_token_is_generic(current))
            if preserve_current and needs_recovery:
                current_norm = self._normalize_token_for_compare(current)
                sample_norms = {
                    self._normalize_token_for_compare(value)
                    for value in (column_values[idx] if idx < len(column_values) else [])
                    if self._normalize_token_for_compare(value)
                }
                temporal_header = bool(
                    re.fullmatch(r"(?:19|20)\d{2}年?", current)
                    or re.fullmatch(r"(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", current)
                )
                if (current_norm and current_norm in sample_norms) or (
                    self.cell_text_numeric_like(current) and not temporal_header
                ):
                    preserve_current = False
                if (
                    preserve_current
                    and idx == 0
                    and not temporal_header
                    and not self.cell_text_numeric_like(current)
                    and not self.header_text_has_label_cue(current)
                    and self.column_numeric_ratio(
                        column_values[idx] if idx < len(column_values) else [],
                        ignore_temporal=True,
                    ) <= 0.25
                ):
                    preserve_current = False
            if preserve_current:
                repaired_headers.append(current)
                continue
            replacement = self.guess_header_from_column_values(
                col_index=idx,
                values=column_values[idx] if idx < len(column_values) else [],
                numeric_rank=numeric_rank_map.get(idx, 0),
                numeric_col_count=len(numeric_positions),
                caption_hint=caption_hint,
            )
            repaired_headers.append(self._normalize_text(replacement) or f"col_{idx + 1}")

        return repaired_headers, repaired_rows

    def infer_headers_and_data_rows(self, rows_payload: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
        if not rows_payload:
            return [], []

        def _row_texts(row: Dict[str, Any]) -> List[str]:
            cells = sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
            return [self._normalize_text(str(cell.get("text", ""))) for cell in cells]

        rows_text = [_row_texts(row) for row in rows_payload]
        row1 = rows_text[0]
        col_count = max(len(row1), max((len(row.get("cells", [])) for row in rows_payload), default=0))

        header_start = 0
        if self.is_caption_like_header_row(row1, col_count) and len(rows_payload) >= 2:
            header_start = 1
            row1 = rows_text[header_start]

        headers = row1[:] if row1 else [f"col_{idx+1}" for idx in range(col_count)]
        data_rows = rows_payload[header_start + 1 :] if len(rows_payload) > (header_start + 1) else []

        if len(rows_payload) >= (header_start + 2):
            row2 = rows_text[header_start + 1]
            if self.is_unit_row(row2):
                merged = self.merge_header_rows(row1, row2, col_count)
                if any(merged):
                    headers = merged
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )
            elif len(rows_payload) >= (header_start + 4) and self.should_merge_hierarchical_header_rows(
                row1, row2, col_count
            ):
                merged = self.merge_header_rows(row1, row2, col_count)
                if any(merged):
                    headers = merged
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )

        if not self.looks_like_header_row(headers):
            if len(rows_payload) >= (header_start + 2):
                alt_header = rows_text[header_start + 1]
                if self.looks_like_header_row(alt_header):
                    headers = alt_header[:]
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )
                else:
                    headers = [f"col_{idx+1}" for idx in range(max(col_count, 1))]
                    data_rows = rows_payload[header_start:]
            else:
                headers = [f"col_{idx+1}" for idx in range(max(col_count, 1))]
                data_rows = rows_payload[header_start:]

        headers = [header if header else f"col_{idx+1}" for idx, header in enumerate(headers)]
        if self.headers_need_recovery(headers):
            data_rows = rows_payload[header_start:]
        headers, data_rows = self.recover_low_signal_headers(headers, data_rows)
        headers = [header if header else f"col_{idx+1}" for idx, header in enumerate(headers)]
        return headers, data_rows

    def should_merge_hierarchical_header_rows(self, row1: List[str], row2: List[str], col_count: int) -> bool:
        if col_count < 4:
            return False
        if int(self._runtime_page_count_provider() or 0) > 120:
            return False
        values1 = [self._normalize_text(value) for value in row1 if self._normalize_text(value)]
        values2 = [self._normalize_text(value) for value in row2 if self._normalize_text(value)]
        if not values1 or not values2:
            return False
        if self.is_unit_row(row2):
            return False
        if self._contains_figure_marker(" ".join(values1 + values2)):
            return False
        if not self.looks_like_header_row(row2):
            return False

        fill1 = len(values1) / float(max(col_count, 1))
        fill2 = len(values2) / float(max(col_count, 1))
        numeric_like2 = sum(
            1
            for value in values2
            if re.search(r"\d", value) and not re.search(r"[A-Za-z\u4e00-\u9fa5]", value)
        )
        numeric_ratio2 = numeric_like2 / float(max(len(values2), 1))

        if numeric_ratio2 > 0.45:
            return False
        if fill1 <= 0.6 and fill2 >= 0.55 and len(values2) >= 2:
            return True
        if fill1 <= 0.5 and len(values2) >= 3:
            return True
        return False

    def is_caption_like_header_row(self, values: List[str], col_count: int) -> bool:
        non_empty = [self._normalize_text(value) for value in values if self._normalize_text(value)]
        if not non_empty:
            return False
        joined = " ".join(non_empty)
        lower = joined.lower()
        if len(non_empty) <= 2:
            if re.search(r"\btable\b\s*[a-z0-9.\-]*", lower):
                return True
            if re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]*", joined):
                return True
            if "续表" in joined:
                return True
        if len(non_empty) == 1 and len(non_empty[0]) >= 20:
            if self._contains_catalog_marker(joined):
                return True
            if re.search(r"\btable\b", lower):
                return True
        if len(non_empty) <= max(2, col_count // 3) and self._contains_catalog_marker(joined):
            return True
        return False

    def is_unit_row(self, values: List[str]) -> bool:
        if not values:
            return False
        non_empty = [value for value in values if value]
        if not non_empty:
            return False
        unit_like = sum(1 for value in non_empty if self.is_unit_like_token(value))
        return unit_like / float(len(non_empty)) >= 0.6

    @staticmethod
    def looks_like_header_row(headers: List[str]) -> bool:
        values = [header.strip() for header in headers if header and header.strip()]
        if not values:
            return False
        numeric_only = sum(1 for value in values if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", value))
        if numeric_only / float(len(values)) > 0.5:
            return False
        return True

    def drop_redundant_header_like_rows(self, rows_payload: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
        if not rows_payload:
            return rows_payload
        header_norm = [self._normalize_token_for_compare(header) for header in headers]
        filtered: List[Dict[str, Any]] = []
        for row in rows_payload:
            cells = sorted(row.get("cells", []), key=lambda cell: int(cell.get("col_index", 0) or 0))
            row_values = [self._normalize_token_for_compare(str(cell.get("text", ""))) for cell in cells]
            row_values = row_values[: len(header_norm)]
            if not row_values:
                continue

            match = 0
            comparable = 0
            has_number = False
            for idx, value in enumerate(row_values):
                if not value:
                    continue
                if re.search(r"\d", value):
                    has_number = True
                header_value = header_norm[idx] if idx < len(header_norm) else ""
                if header_value:
                    comparable += 1
                    if value == header_value:
                        match += 1
            ratio = (match / float(comparable)) if comparable else 0.0
            if ratio >= 0.7 and not has_number:
                continue
            filtered.append(row)
        return filtered
