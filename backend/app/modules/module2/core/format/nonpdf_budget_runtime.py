from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class NonPdfBudgetPlan:
    parse_timeout_sec: float
    extract_timeout_sec: float
    nonpdf_total_budget_sec: Optional[float]
    word_parse_extract_budget_sec: Optional[float]
    word_convert_budget_sec: Optional[float]


@dataclass(frozen=True)
class ConversionTimeoutDecision:
    timeout_sec: Optional[float]
    exhausted_detail: str = ""


@dataclass(frozen=True)
class ParseBudgetTightenDecision:
    parse_timeout_sec: float
    extract_timeout_sec: float
    warning: str = ""

    @property
    def tightened(self) -> bool:
        return bool(self.warning)


class NonPdfBudgetRuntime:
    """Resolve non-PDF parse/extract/conversion budgets without touching I/O."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    def resolve_nonpdf_plan(
        self,
        *,
        file_name: str,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: Optional[float],
        nonpdf_guard_sec: float,
        is_word_file: bool,
    ) -> NonPdfBudgetPlan:
        parse_timeout = float(parse_timeout_sec)
        extract_timeout = float(extract_timeout_sec)
        total_budget = float(nonpdf_total_budget_sec) if nonpdf_total_budget_sec is not None else None
        word_parse_extract_budget_sec: Optional[float] = None
        word_convert_budget_sec: Optional[float] = None

        if str(file_name or "").lower().endswith(".xlsx"):
            parse_timeout = max(parse_timeout, float(self._getenv("MODULE2_XLSX_PARSE_TIMEOUT_SEC", "32")))
            extract_timeout = max(extract_timeout, float(self._getenv("MODULE2_XLSX_EXTRACT_TIMEOUT_SEC", "96")))
            if total_budget is not None:
                total_budget = max(total_budget, float(self._getenv("MODULE2_XLSX_TOTAL_BUDGET_SEC", "140")))

        if is_word_file:
            if total_budget is not None:
                total_budget = max(total_budget, float(self._getenv("MODULE2_WORD_TOTAL_BUDGET_SEC", "150")))
            parse_timeout = max(parse_timeout, float(self._getenv("MODULE2_WORD_PARSE_TIMEOUT_SEC", "42")))
            extract_timeout = max(extract_timeout, float(self._getenv("MODULE2_WORD_EXTRACT_TIMEOUT_SEC", "72")))
            word_parse_extract_budget_sec = max(
                32.0,
                float(self._getenv("MODULE2_WORD_PARSE_EXTRACT_BUDGET_SEC", "96")),
            )
            word_convert_budget_sec = max(
                15.0,
                float(self._getenv("MODULE2_WORD_CONVERT_BUDGET_SEC", "30")),
            )
            if total_budget is not None:
                max_convert_budget = max(12.0, total_budget - 20.0)
                word_convert_budget_sec = min(word_convert_budget_sec, max_convert_budget)
                parse_extract_cap = max(
                    18.0,
                    total_budget - word_convert_budget_sec - float(nonpdf_guard_sec),
                )
                word_parse_extract_budget_sec = min(word_parse_extract_budget_sec, parse_extract_cap)
            parse_extract_total = parse_timeout + extract_timeout
            if word_parse_extract_budget_sec is not None and parse_extract_total > word_parse_extract_budget_sec:
                ratio = word_parse_extract_budget_sec / max(parse_extract_total, 1e-6)
                parse_timeout = max(5.0, parse_timeout * ratio)
                extract_timeout = max(8.0, extract_timeout * ratio)
                parse_extract_total = parse_timeout + extract_timeout
            if parse_extract_total > 12.0:
                target_parse_share = max(
                    0.42,
                    min(0.78, float(self._getenv("MODULE2_WORD_PARSE_SHARE", "0.50"))),
                )
                min_word_parse_timeout = max(
                    18.0,
                    float(self._getenv("MODULE2_WORD_PARSE_TIMEOUT_MIN_SEC", "32")),
                )
                target_parse_timeout = max(
                    parse_timeout,
                    parse_extract_total * target_parse_share,
                    min_word_parse_timeout,
                )
                parse_timeout = min(target_parse_timeout, parse_extract_total - 8.0)
                extract_timeout = max(8.0, parse_extract_total - parse_timeout)
                min_word_extract_timeout = max(
                    24.0,
                    float(self._getenv("MODULE2_WORD_EXTRACT_TIMEOUT_MIN_SEC", "56")),
                )
                if extract_timeout < min_word_extract_timeout:
                    parse_timeout = max(
                        min_word_parse_timeout,
                        parse_extract_total - min_word_extract_timeout,
                    )
                    extract_timeout = max(8.0, parse_extract_total - parse_timeout)

        return NonPdfBudgetPlan(
            parse_timeout_sec=parse_timeout,
            extract_timeout_sec=extract_timeout,
            nonpdf_total_budget_sec=total_budget,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
        )

    def apply_field_extract_timeout_floor(self, *, extract_timeout_sec: float) -> float:
        return max(
            float(extract_timeout_sec),
            max(8.0, float(self._getenv("MODULE2_FIELD_EXTRACT_TIMEOUT_SEC", "90"))),
        )

    @staticmethod
    def resolve_conversion_timeout(
        *,
        file_name: str,
        conversion_label: str,
        convert_timeout_default: float,
        word_convert_budget_sec: Optional[float],
        nonpdf_total_budget_sec: Optional[float],
        elapsed_before_convert_sec: float,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_guard_sec: float,
    ) -> ConversionTimeoutDecision:
        convert_timeout_sec = float(convert_timeout_default)
        if word_convert_budget_sec is not None:
            convert_timeout_sec = min(convert_timeout_sec, max(12.0, float(word_convert_budget_sec)))
        if nonpdf_total_budget_sec is not None:
            remaining_for_convert = (
                float(nonpdf_total_budget_sec)
                - max(0.0, float(elapsed_before_convert_sec))
                - (float(parse_timeout_sec) + float(extract_timeout_sec) + float(nonpdf_guard_sec))
            )
            if remaining_for_convert > 0:
                convert_timeout_sec = min(convert_timeout_sec, max(12.0, remaining_for_convert))
            else:
                return ConversionTimeoutDecision(
                    timeout_sec=None,
                    exhausted_detail=f"Non-PDF budget exhausted before {conversion_label} conversion for {file_name}",
                )
        return ConversionTimeoutDecision(timeout_sec=max(12.0, convert_timeout_sec))

    @staticmethod
    def tighten_parse_budgets_before_parse(
        *,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: Optional[float],
        elapsed_before_parse_sec: float,
        nonpdf_guard_sec: float,
    ) -> ParseBudgetTightenDecision:
        parse_timeout = float(parse_timeout_sec)
        extract_timeout = float(extract_timeout_sec)
        if nonpdf_total_budget_sec is None:
            return ParseBudgetTightenDecision(
                parse_timeout_sec=parse_timeout,
                extract_timeout_sec=extract_timeout,
            )

        remaining_budget = float(nonpdf_total_budget_sec) - max(0.0, float(elapsed_before_parse_sec))
        parse_extract_total = parse_timeout + extract_timeout
        if remaining_budget > 0 and (parse_extract_total + float(nonpdf_guard_sec)) > remaining_budget:
            allowed = max(13.0, remaining_budget - float(nonpdf_guard_sec))
            ratio = allowed / max(parse_extract_total, 1e-6)
            return ParseBudgetTightenDecision(
                parse_timeout_sec=max(5.0, parse_timeout * ratio),
                extract_timeout_sec=max(8.0, extract_timeout * ratio),
                warning="nonpdf_budget_tight",
            )

        return ParseBudgetTightenDecision(
            parse_timeout_sec=parse_timeout,
            extract_timeout_sec=extract_timeout,
        )
