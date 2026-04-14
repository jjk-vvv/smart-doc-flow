from __future__ import annotations

"""Quick table fallback helpers for module2 extraction service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Optional, Set

from ...core.format.xlsx_artifact_io import load_xlsx_sheet_rows_for_table


IsLowValueFieldNameFn = Callable[[Any], bool]
CoerceFieldTypeFn = Callable[[Any], str]
IsLowValueFallbackValueFn = Callable[[Any], bool]
NormalizeBboxFn = Callable[..., Any]
ToNumberOrNoneFn = Callable[[Any], Any]


@dataclass(frozen=True)
class Module2MainQuickExtractBundle:
    to_number_or_none: Callable[[Any], Optional[float]]
    quick_extract_from_tables: Callable[[List[Dict[str, Any]], Dict[str, Any]], Dict[str, Dict[str, Any]]]


@dataclass(frozen=True)
class Module2MainValueGuardBundle:
    is_low_value_quick_fallback_value: Callable[[Any], bool]


def build_module2_main_value_guard_bundle(
    *,
    to_number_or_none: ToNumberOrNoneFn,
    auto_schema_stopwords_en: Set[str],
) -> Module2MainValueGuardBundle:
    def _is_low_value_quick_fallback_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return False

        text = str(value).strip()
        if not text:
            return True
        if to_number_or_none(text) is not None:
            return False

        lower_text = re.sub(r"\s+", " ", text).strip().lower()
        if len(lower_text) <= 2 and not re.search(r"[\u4e00-\u9fff]", lower_text):
            return True
        if lower_text in auto_schema_stopwords_en:
            return True
        if re.match(r"^[\(\[]?(?:fig(?:ure)?|eqn|equation|table)\b", lower_text):
            return True

        alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", lower_text)]
        if alpha_tokens and all(tok in auto_schema_stopwords_en for tok in alpha_tokens):
            return True
        return False

    return Module2MainValueGuardBundle(
        is_low_value_quick_fallback_value=_is_low_value_quick_fallback_value,
    )


def build_module2_main_quick_extract_bundle(
    *,
    is_low_value_auto_schema_field_name: IsLowValueFieldNameFn,
    coerce_field_type: CoerceFieldTypeFn,
    is_low_value_quick_fallback_value: IsLowValueFallbackValueFn,
    normalize_bbox: NormalizeBboxFn,
) -> Module2MainQuickExtractBundle:
    def _all_table_blocks_are_spreadsheet_sources(table_blocks: List[Dict[str, Any]]) -> bool:
        if not table_blocks:
            return False
        for table in table_blocks:
            source = str((table or {}).get("source") or "").strip().lower()
            if source not in {"xlsx", "xlsx_formula"}:
                return False
        return True

    def _iter_candidate_rows(table: Dict[str, Any]) -> List[Dict[str, Any]]:
        artifact_rows = load_xlsx_sheet_rows_for_table(table)
        if artifact_rows:
            return artifact_rows
        rows = table.get("rows")
        return list(rows or []) if isinstance(rows, list) else []

    def _tokenize_field_hint(field_name: str) -> Set[str]:
        text = str(field_name or "").strip().lower()
        if not text:
            return set()
        normalized = re.sub(r"[\s_:/\-]+", "", text)
        tokens: Set[str] = set()
        if len(normalized) >= 2:
            tokens.add(normalized)
        for token in re.split(r"[\s_:/\-()]+", text):
            t = token.strip()
            if len(t) >= 2:
                tokens.add(t)
        if re.search(r"[\u4e00-\u9fff]", normalized):
            for idx in range(0, max(0, len(normalized) - 1)):
                frag = normalized[idx : idx + 2]
                if len(frag) == 2:
                    tokens.add(frag)
        return {tok for tok in tokens if tok}

    def _to_number_or_none(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        cleaned = re.sub(r"[^0-9eE+\-\.]", "", text)
        try:
            return float(cleaned)
        except Exception:
            return None

    def _quick_extract_from_tables(
        table_blocks: List[Dict[str, Any]],
        schema_fields: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not table_blocks or not schema_fields:
            return out

        spreadsheet_only = _all_table_blocks_are_spreadsheet_sources(table_blocks)
        table_iter = table_blocks if spreadsheet_only else table_blocks[:12]
        for field_name, field_type in schema_fields.items():
            if is_low_value_auto_schema_field_name(field_name):
                continue
            tokens = _tokenize_field_hint(str(field_name))
            if not tokens:
                continue
            wants_number = coerce_field_type(field_type) == "number"
            best_score = -1
            best_item: Optional[Dict[str, Any]] = None

            for table in table_iter:
                row_iter = _iter_candidate_rows(table)
                if not spreadsheet_only:
                    row_iter = row_iter[:120]
                for row in row_iter:
                    if not isinstance(row, dict):
                        continue
                    cells = list(row.get("cells") or [])
                    if not spreadsheet_only:
                        cells = cells[:24]
                    for cell in cells:
                        if not isinstance(cell, dict):
                            continue
                        text = str(cell.get("text") or "").strip()
                        if not text:
                            continue
                        header = str(cell.get("header") or "").strip()
                        merged_header = re.sub(r"\s+", "", f"{header}".lower())
                        merged_text = re.sub(r"\s+", "", text.lower())
                        header_score = sum(2 for tok in tokens if tok in merged_header)
                        text_score = sum(1 for tok in tokens if tok in merged_text)
                        score = header_score + text_score
                        if score <= 0:
                            continue

                        value: Any = text
                        if wants_number:
                            numeric = _to_number_or_none(cell.get("numeric_value"))
                            if numeric is None:
                                numeric = _to_number_or_none(text)
                            if numeric is None:
                                continue
                            value = numeric
                        elif is_low_value_quick_fallback_value(text):
                            continue

                        if score > best_score:
                            best_score = score
                            best_item = {
                                "value": value,
                                "confidence": min(0.95, 0.55 + 0.08 * float(score)),
                                "source_ref_id": str(cell.get("ref_id") or "").strip() or None,
                                "bbox": normalize_bbox(
                                    cell.get("bbox"),
                                    page_hint=int(table.get("page", 1) or 1),
                                ),
                            }
                        if best_score >= 6:
                            break
                    if best_score >= 6:
                        break
                if best_score >= 6:
                    break

            if best_item is not None:
                out[str(field_name)] = best_item
        return out

    return Module2MainQuickExtractBundle(
        to_number_or_none=_to_number_or_none,
        quick_extract_from_tables=_quick_extract_from_tables,
    )
