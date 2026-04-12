from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple


NormalizeText = Callable[[str], str]
NormalizeTokenForCompare = Callable[[str], str]
FigureTextIsLowSignal = Callable[[str], bool]
StripFigureCaptionNoise = Callable[[str], str]
HeaderTokenIsGeneric = Callable[[str], bool]
NormalizeDataframeHeaders = Callable[..., List[str]]
NormalizeDataframeMatrix = Callable[..., List[List[str]]]
FigureAxisDimensionLabel = Callable[..., str]
HeadersNeedRecovery = Callable[[List[str]], bool]
RecoverLowSignalHeaders = Callable[..., Tuple[List[str], List[Dict[str, Any]]]]


_FIGURE_INDEX_TOKEN_PATTERN = (
    r"[0-9A-Za-z\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343]+"
    r"(?:[-._][0-9A-Za-z\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343]+)*"
)
_FIGURE_PREFIX_PATTERN = rf"(?:fig(?:ure)?|[\u56fe\u5716])\.?\s*{_FIGURE_INDEX_TOKEN_PATTERN}"
_UNIT_LABEL_PATTERN = r"(?:unit|\u5355\u4f4d)"
_UNIT_VALUE_PATTERN = r"[A-Za-z0-9\u4e00-\u9fff%‰℃°/._ \-]{1,24}"
_FIGURE_GENERIC_HEADER_NAMES = {
    "year",
    "date",
    "region",
    "category",
    "\u5e74\u4efd",
    "\u65e5\u671f",
    "\u5730\u533a",
    "\u7c7b\u522b",
}
_FALLBACK_LABEL_PATTERN = r"[A-Za-z\u4e00-\u9fa5/_%‰℃°-]{0,18}"


class FigureTextRuntime:
    """Pure figure-text normalization rules shared across figure-related runtimes."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        header_token_is_generic: HeaderTokenIsGeneric,
    ) -> None:
        self._normalize_text = normalize_text
        self._header_token_is_generic = header_token_is_generic

    @staticmethod
    def count_figure_markers_in_text(text: str) -> int:
        return len(re.findall(_FIGURE_PREFIX_PATTERN, str(text or ""), flags=re.IGNORECASE))

    def strip_figure_caption_noise(self, text: str) -> str:
        cleaned = self._normalize_text(str(text or ""))
        if not cleaned:
            return ""
        cleaned = re.sub(
            rf"^\s*{_FIGURE_PREFIX_PATTERN}\s*[:：.\-、]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"\(\s*{_UNIT_LABEL_PATTERN}\s*[:：]\s*[^()]+?\)\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"{_UNIT_LABEL_PATTERN}\s*[:：]\s*{_UNIT_VALUE_PATTERN}\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^[：:、，,;；.\- ]+", "", cleaned)
        cleaned = re.sub(r"[：:、，,;；.\- ]+$", "", cleaned)
        return self._normalize_text(cleaned)

    def figure_text_is_low_signal(self, text: str) -> bool:
        cleaned = self._normalize_text(str(text or ""))
        if not cleaned:
            return True
        lowered = cleaned.lower()
        if self._header_token_is_generic(cleaned):
            return True
        if re.fullmatch(
            rf"{_UNIT_LABEL_PATTERN}\s*[:：]\s*{_UNIT_VALUE_PATTERN}",
            cleaned,
            flags=re.IGNORECASE,
        ):
            return True
        if lowered.startswith("the unit of measurement is"):
            return True
        if lowered.startswith("the image contains the text"):
            probe = self._normalize_text(re.sub(r"^the image contains the text\s*", "", cleaned, flags=re.IGNORECASE))
            if not probe or re.fullmatch(
                rf"['\"“”‘’\s:：-]*(?:{_UNIT_LABEL_PATTERN})[^A-Za-z\u4e00-\u9fff0-9]*.*",
                probe,
                flags=re.IGNORECASE,
            ):
                return True
        semantic = self.strip_figure_caption_noise(cleaned)
        if not semantic and self.count_figure_markers_in_text(cleaned) <= 1:
            return True
        return False


class FigureMatchingRuntime:
    """Match DOCX chart XML titles to recovered PDF figure captions."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        normalize_token_for_compare: NormalizeTokenForCompare,
    ) -> None:
        self._normalize_text = normalize_text
        self._normalize_token_for_compare = normalize_token_for_compare

    def find_matching_pdf_figure_index(
        self,
        *,
        chart_title: str,
        figure_blocks: List[Dict[str, Any]],
    ) -> Optional[int]:
        title_norm = self._normalize_token_for_compare(chart_title)
        if not title_norm:
            return None

        title_marker = self.extract_figure_marker(chart_title)
        best_idx: Optional[int] = None
        best_score = 0
        for idx, figure in enumerate(figure_blocks):
            caption = self._normalize_text(str(figure.get("caption", "") or ""))
            caption_norm = self._normalize_token_for_compare(caption)
            if not caption_norm:
                continue

            score = 0
            if title_norm == caption_norm:
                score += 100
            elif title_norm in caption_norm or caption_norm in title_norm:
                score += 85
            if title_marker and title_marker == self.extract_figure_marker(caption):
                score += 35

            overlap = len(set(title_norm) & set(caption_norm))
            score += min(20, overlap)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_score < 40:
            return None
        return best_idx

    @staticmethod
    def extract_figure_marker(text: str) -> str:
        match = re.search(
            rf"(?:fig(?:ure)?|[\u56fe\u5716])[\s._:-]*({_FIGURE_INDEX_TOKEN_PATTERN})",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return str(match.group(1) or "").strip().lower()


class FigureSemanticsRuntime:
    """Normalize figure payload semantics into stable titles, captions, and dataframes."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        figure_text_is_low_signal: FigureTextIsLowSignal,
        strip_figure_caption_noise: StripFigureCaptionNoise,
        header_token_is_generic: HeaderTokenIsGeneric,
        normalize_dataframe_headers: NormalizeDataframeHeaders,
        normalize_dataframe_matrix: NormalizeDataframeMatrix,
        figure_axis_dimension_label: FigureAxisDimensionLabel,
        headers_need_recovery: HeadersNeedRecovery,
        recover_low_signal_headers: RecoverLowSignalHeaders,
    ) -> None:
        self._normalize_text = normalize_text
        self._figure_text_is_low_signal = figure_text_is_low_signal
        self._strip_figure_caption_noise = strip_figure_caption_noise
        self._header_token_is_generic = header_token_is_generic
        self._normalize_dataframe_headers = normalize_dataframe_headers
        self._normalize_dataframe_matrix = normalize_dataframe_matrix
        self._figure_axis_dimension_label = figure_axis_dimension_label
        self._headers_need_recovery = headers_need_recovery
        self._recover_low_signal_headers = recover_low_signal_headers

    def recover_figure_title_and_caption(
        self,
        *,
        title: str,
        caption: str,
        key_points: List[str],
        text_blocks: List[str],
        fallback_texts: List[str],
        dataframe_headers: List[str],
        series_labels: List[str],
        x_axis: str = "",
        y_axis: str = "",
    ) -> Tuple[str, str]:
        normalized_title = self._normalize_text(title)
        normalized_caption = self._normalize_text(caption)
        if self._figure_text_is_low_signal(normalized_title):
            normalized_title = ""
        if self._figure_text_is_low_signal(normalized_caption):
            normalized_caption = ""

        semantic_caption = self._strip_figure_caption_noise(normalized_caption)
        semantic_title = self._strip_figure_caption_noise(normalized_title)

        candidate_pool: List[str] = []
        if semantic_title:
            candidate_pool.append(semantic_title)
        if semantic_caption:
            candidate_pool.append(semantic_caption)
        for item in key_points + text_blocks + fallback_texts:
            probe = self._strip_figure_caption_noise(item)
            if probe and not self._figure_text_is_low_signal(probe):
                candidate_pool.append(probe)
        meaningful_headers = [
            self._normalize_text(header)
            for header in dataframe_headers
            if self._normalize_text(header) and not self._header_token_is_generic(self._normalize_text(header))
        ]
        preferred_headers = [header for header in meaningful_headers if header.lower() not in _FIGURE_GENERIC_HEADER_NAMES]
        if preferred_headers:
            candidate_pool.append(" / ".join(preferred_headers[:2]))
        elif series_labels:
            candidate_pool.append(" / ".join(series_labels[:2]))
        elif y_axis:
            candidate_pool.append(self._normalize_text(y_axis))
        elif x_axis:
            candidate_pool.append(self._normalize_text(x_axis))

        recovered_title = ""
        for candidate in candidate_pool:
            probe = self._normalize_text(candidate)
            if probe and not self._figure_text_is_low_signal(probe):
                recovered_title = probe
                break

        recovered_caption = normalized_caption
        if not recovered_caption and recovered_title:
            recovered_caption = recovered_title
        if not recovered_title and semantic_caption:
            recovered_title = semantic_caption
        return recovered_title, recovered_caption

    def coerce_figure_dataframe(
        self,
        *,
        headers: List[str],
        rows: List[List[str]],
        key_values: List[Dict[str, str]],
        fallback_texts: List[str],
        caption_hint: str = "",
        series_labels: Optional[List[str]] = None,
        x_axis: str = "",
        y_axis: str = "",
    ) -> Tuple[List[str], List[List[str]], str]:
        normalized_headers = self._normalize_dataframe_headers(headers)
        normalized_rows = self._normalize_dataframe_matrix(rows)
        normalized_series_labels = [self._normalize_text(label) for label in list(series_labels or []) if self._normalize_text(label)]

        if normalized_rows:
            max_cols = max((len(row) for row in normalized_rows), default=0)
            if not normalized_headers:
                if max_cols == 2 and (x_axis or y_axis):
                    normalized_headers = [
                        self._normalize_text(x_axis or "\u7ef4\u5ea6"),
                        self._normalize_text(y_axis or "\u6570\u503c"),
                    ]
                elif max_cols >= 2 and len(normalized_series_labels) >= (max_cols - 1):
                    first_column_values = [row[0] for row in normalized_rows if row]
                    first_header = self._figure_axis_dimension_label(first_column_values)
                    normalized_headers = [first_header] + normalized_series_labels[: max_cols - 1]
                elif max_cols == 3:
                    normalized_headers = ["\u6307\u6807", "\u503c", "\u5355\u4f4d"]
                elif max_cols > 0:
                    normalized_headers = [f"\u5217_{i + 1}" for i in range(max_cols)]
            if normalized_headers and max_cols > 0 and self._headers_need_recovery(normalized_headers):
                if max_cols >= 2 and len(normalized_series_labels) >= (max_cols - 1):
                    first_column_values = [row[0] for row in normalized_rows if row]
                    first_header = self._figure_axis_dimension_label(first_column_values)
                    normalized_headers = [first_header] + normalized_series_labels[: max_cols - 1]
                else:
                    rows_payload: List[Dict[str, Any]] = []
                    for row_idx, row in enumerate(normalized_rows, start=1):
                        cells = []
                        for col_idx, value in enumerate(row, start=1):
                            if not self._normalize_text(value):
                                continue
                            cells.append({"col_index": col_idx, "text": value})
                        if cells:
                            rows_payload.append({"row_index": row_idx, "cells": cells})
                    normalized_headers, _ = self._recover_low_signal_headers(
                        normalized_headers,
                        rows_payload,
                        caption=caption_hint,
                        notes=fallback_texts[:6],
                    )
                normalized_headers = [
                    self._normalize_text(item) or f"\u5217_{i + 1}"
                    for i, item in enumerate(normalized_headers[:max_cols])
                ]
                if len(normalized_headers) < max_cols:
                    normalized_headers.extend([f"\u5217_{i + 1}" for i in range(len(normalized_headers), max_cols)])
            return normalized_headers, normalized_rows, "model"

        key_value_rows: List[List[str]] = []
        for item in key_values:
            name = self._normalize_text(item.get("name", ""))
            value = self._normalize_text(item.get("value", ""))
            unit = self._normalize_text(item.get("unit", ""))
            if not name and not value:
                continue
            key_value_rows.append([name or f"\u6307\u6807{len(key_value_rows) + 1}", value, unit])
        if key_value_rows:
            return ["\u6307\u6807", "\u503c", "\u5355\u4f4d"], key_value_rows, "key_values"

        parsed_rows: List[List[str]] = []
        for raw in fallback_texts:
            text = self._normalize_text(str(raw or ""))
            if not text:
                continue
            match = re.match(
                rf"^(.{{1,72}}?)[：:]\s*([-+]?(?:\d[\d,]*\.?\d*|\d*\.?\d+)(?:[%％‰]?)?)\s*({_FALLBACK_LABEL_PATTERN})$",
                text,
            )
            if not match:
                match = re.match(
                    rf"^(.{{1,56}}?)\s+([-+]?(?:\d[\d,]*\.?\d*|\d*\.?\d+)(?:[%％‰]?)?)\s*({_FALLBACK_LABEL_PATTERN})$",
                    text,
                )
            if not match:
                continue
            label = self._normalize_text(match.group(1))
            value = self._normalize_text(match.group(2))
            unit = self._normalize_text(match.group(3))
            if not label or not value:
                continue
            parsed_rows.append([label, value, unit])
        if parsed_rows:
            return ["\u6307\u6807", "\u503c", "\u5355\u4f4d"], parsed_rows, "text_blocks"

        return normalized_headers, [], "none"
