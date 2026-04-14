from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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


document_flow_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_pipeline_runtime.py"],
    "_smart_doc_flow_module2_document_pipeline_runtime_for_input_plan",
)

DocumentInputPlanRuntime = document_flow_runtime_module.DocumentInputPlanRuntime


class _NonPdfPlan:
    def __init__(
        self,
        *,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: float | None,
        word_parse_extract_budget_sec: float | None,
        word_convert_budget_sec: float | None,
    ) -> None:
        self.parse_timeout_sec = parse_timeout_sec
        self.extract_timeout_sec = extract_timeout_sec
        self.nonpdf_total_budget_sec = nonpdf_total_budget_sec
        self.word_parse_extract_budget_sec = word_parse_extract_budget_sec
        self.word_convert_budget_sec = word_convert_budget_sec


def test_document_input_plan_runtime_keeps_pdf_defaults_and_floor() -> None:
    runtime = DocumentInputPlanRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_PARSE_TIMEOUT_SEC": "120",
            "MODULE2_EXTRACT_TIMEOUT_SEC": "140",
            "MODULE2_NONPDF_BUDGET_GUARD_SEC": "3.0",
        }.get(key, default)
    )

    outcome = runtime.build_plan(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        preflight_nonpdf_profile=lambda **kwargs: (_ for _ in ()).throw(AssertionError("pdf should skip preflight")),
        resolve_nonpdf_budgets=lambda profile: (_ for _ in ()).throw(AssertionError("pdf should skip budgets")),
        resolve_nonpdf_plan=lambda **kwargs: (_ for _ in ()).throw(AssertionError("pdf should skip plan")),
        apply_field_extract_timeout_floor=lambda *, extract_timeout_sec: extract_timeout_sec + 10.0,
        word_pdf_required=lambda: True,
        is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
    )

    assert outcome.parse_timeout_sec == 120.0
    assert outcome.extract_timeout_sec == 150.0
    assert outcome.nonpdf_preflight is None
    assert outcome.nonpdf_budget is None
    assert outcome.nonpdf_total_budget_sec is None
    assert outcome.nonpdf_guard_sec == 3.0
    assert outcome.word_parse_extract_budget_sec is None
    assert outcome.word_convert_budget_sec is None
    assert outcome.word_parse_via_pdf is True
    assert outcome.input_is_word is False


def test_document_input_plan_runtime_builds_nonpdf_word_plan() -> None:
    runtime = DocumentInputPlanRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_PARSE_TIMEOUT_SEC": "150",
            "MODULE2_EXTRACT_TIMEOUT_SEC": "150",
            "MODULE2_NONPDF_BUDGET_GUARD_SEC": "2.0",
        }.get(key, default)
    )
    captured: dict[str, object] = {}

    def _resolve_nonpdf_plan(**kwargs):
        captured["resolve_nonpdf_plan"] = dict(kwargs)
        return _NonPdfPlan(
            parse_timeout_sec=36.0,
            extract_timeout_sec=66.0,
            nonpdf_total_budget_sec=110.0,
            word_parse_extract_budget_sec=88.0,
            word_convert_budget_sec=24.0,
        )

    outcome = runtime.build_plan(
        file_name="report.docx",
        file_bytes=b"docx",
        preflight_nonpdf_profile=lambda **kwargs: {"profile": "mixed", "signals": {"tables": 2}},
        resolve_nonpdf_budgets=lambda profile: {
            "parse_timeout_sec": 24.0,
            "extract_timeout_sec": 44.0,
            "total_budget_sec": 90.0,
        },
        resolve_nonpdf_plan=_resolve_nonpdf_plan,
        apply_field_extract_timeout_floor=lambda *, extract_timeout_sec: extract_timeout_sec + 5.0,
        word_pdf_required=lambda: False,
        is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
    )

    assert outcome.parse_timeout_sec == 36.0
    assert outcome.extract_timeout_sec == 71.0
    assert outcome.nonpdf_preflight == {"profile": "mixed", "signals": {"tables": 2}}
    assert outcome.nonpdf_budget == {
        "parse_timeout_sec": 24.0,
        "extract_timeout_sec": 44.0,
        "total_budget_sec": 90.0,
    }
    assert outcome.nonpdf_total_budget_sec == 110.0
    assert outcome.word_parse_extract_budget_sec == 88.0
    assert outcome.word_convert_budget_sec == 24.0
    assert outcome.word_parse_via_pdf is False
    assert outcome.input_is_word is True
    assert captured["resolve_nonpdf_plan"] == {
        "file_name": "report.docx",
        "parse_timeout_sec": 24.0,
        "extract_timeout_sec": 44.0,
        "nonpdf_total_budget_sec": 90.0,
        "nonpdf_guard_sec": 2.0,
        "is_word_file": True,
    }
