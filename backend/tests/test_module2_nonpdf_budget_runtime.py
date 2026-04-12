from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


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


nonpdf_budget_runtime_module = _load_module(
    ["module2", "app", "core", "format", "nonpdf_budget_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_budget_runtime",
)

NonPdfBudgetRuntime = nonpdf_budget_runtime_module.NonPdfBudgetRuntime


def test_nonpdf_budget_runtime_expands_xlsx_plan_from_profile_budget() -> None:
    env = {
        "MODULE2_XLSX_PARSE_TIMEOUT_SEC": "32",
        "MODULE2_XLSX_EXTRACT_TIMEOUT_SEC": "96",
        "MODULE2_XLSX_TOTAL_BUDGET_SEC": "140",
    }
    runtime = NonPdfBudgetRuntime(getenv=lambda name, default="": env.get(name, default))

    plan = runtime.resolve_nonpdf_plan(
        file_name="report.xlsx",
        parse_timeout_sec=18.0,
        extract_timeout_sec=44.0,
        nonpdf_total_budget_sec=90.0,
        nonpdf_guard_sec=2.0,
        is_word_file=False,
    )

    assert plan.parse_timeout_sec == 32.0
    assert plan.extract_timeout_sec == 96.0
    assert plan.nonpdf_total_budget_sec == 140.0
    assert plan.word_parse_extract_budget_sec is None
    assert plan.word_convert_budget_sec is None


def test_nonpdf_budget_runtime_rebalances_word_parse_and_extract_budgets() -> None:
    env = {
        "MODULE2_WORD_TOTAL_BUDGET_SEC": "100",
        "MODULE2_WORD_PARSE_TIMEOUT_SEC": "42",
        "MODULE2_WORD_EXTRACT_TIMEOUT_SEC": "72",
        "MODULE2_WORD_PARSE_EXTRACT_BUDGET_SEC": "60",
        "MODULE2_WORD_CONVERT_BUDGET_SEC": "25",
        "MODULE2_WORD_PARSE_SHARE": "0.50",
        "MODULE2_WORD_PARSE_TIMEOUT_MIN_SEC": "20",
        "MODULE2_WORD_EXTRACT_TIMEOUT_MIN_SEC": "24",
    }
    runtime = NonPdfBudgetRuntime(getenv=lambda name, default="": env.get(name, default))

    plan = runtime.resolve_nonpdf_plan(
        file_name="report.docx",
        parse_timeout_sec=24.0,
        extract_timeout_sec=40.0,
        nonpdf_total_budget_sec=90.0,
        nonpdf_guard_sec=2.0,
        is_word_file=True,
    )

    assert plan.nonpdf_total_budget_sec == 100.0
    assert plan.word_parse_extract_budget_sec == 60.0
    assert plan.word_convert_budget_sec == 25.0
    assert plan.parse_timeout_sec == pytest.approx(30.0)
    assert plan.extract_timeout_sec == pytest.approx(30.0)


def test_nonpdf_budget_runtime_applies_field_extract_timeout_floor() -> None:
    runtime = NonPdfBudgetRuntime(
        getenv=lambda name, default="": "88" if name == "MODULE2_FIELD_EXTRACT_TIMEOUT_SEC" else default
    )

    assert runtime.apply_field_extract_timeout_floor(extract_timeout_sec=40.0) == 88.0
    assert runtime.apply_field_extract_timeout_floor(extract_timeout_sec=96.0) == 96.0


def test_nonpdf_budget_runtime_resolves_conversion_timeout_with_budget_cap() -> None:
    decision = NonPdfBudgetRuntime.resolve_conversion_timeout(
        file_name="report.docx",
        conversion_label="Word->PDF",
        convert_timeout_default=60.0,
        word_convert_budget_sec=18.0,
        nonpdf_total_budget_sec=80.0,
        elapsed_before_convert_sec=15.0,
        parse_timeout_sec=30.0,
        extract_timeout_sec=20.0,
        nonpdf_guard_sec=2.0,
    )

    assert decision.exhausted_detail == ""
    assert decision.timeout_sec == 13.0


def test_nonpdf_budget_runtime_reports_exhausted_conversion_budget() -> None:
    decision = NonPdfBudgetRuntime.resolve_conversion_timeout(
        file_name="report.doc",
        conversion_label="DOC->DOCX",
        convert_timeout_default=45.0,
        word_convert_budget_sec=20.0,
        nonpdf_total_budget_sec=50.0,
        elapsed_before_convert_sec=5.0,
        parse_timeout_sec=30.0,
        extract_timeout_sec=20.0,
        nonpdf_guard_sec=2.0,
    )

    assert decision.timeout_sec is None
    assert decision.exhausted_detail == "Non-PDF budget exhausted before DOC->DOCX conversion for report.doc"


def test_nonpdf_budget_runtime_tightens_parse_and_extract_before_parse() -> None:
    decision = NonPdfBudgetRuntime.tighten_parse_budgets_before_parse(
        parse_timeout_sec=30.0,
        extract_timeout_sec=40.0,
        nonpdf_total_budget_sec=60.0,
        elapsed_before_parse_sec=15.0,
        nonpdf_guard_sec=2.0,
    )

    assert decision.tightened is True
    assert decision.warning == "nonpdf_budget_tight"
    assert decision.parse_timeout_sec == pytest.approx(18.4285714286)
    assert decision.extract_timeout_sec == pytest.approx(24.5714285714)
