from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_nonpdf_bundle_module = import_module("app.modules.module2.bootstrap.nonpdf")


def test_build_module2_main_nonpdf_bundle_exposes_expected_nonpdf_helpers() -> None:
    env_values = {
        "MODULE2_PARSE_TIMEOUT_SEC": "120",
        "MODULE2_EXTRACT_TIMEOUT_SEC": "150",
        "MODULE2_NONPDF_TOTAL_BUDGET_SEC": "90",
        "MODULE2_NONPDF_PARSE_TEXT_SEC": "24",
        "MODULE2_NONPDF_PARSE_MIXED_SEC": "34",
        "MODULE2_NONPDF_PARSE_CHART_SEC": "42",
        "MODULE2_NONPDF_PARSE_TABLE_SEC": "24",
        "MODULE2_NONPDF_EXTRACT_TEXT_SEC": "34",
        "MODULE2_NONPDF_EXTRACT_MIXED_SEC": "44",
        "MODULE2_NONPDF_EXTRACT_CHART_SEC": "52",
        "MODULE2_NONPDF_EXTRACT_TABLE_SEC": "64",
        "MODULE2_NONPDF_TOTAL_BUDGET_TABLE_SEC": "88",
    }
    bundle = main_nonpdf_bundle_module.build_module2_main_nonpdf_bundle(
        getenv=lambda name, default=None: env_values.get(name, default),
    )

    assert bundle.decode_text_with_fallback("hello".encode("utf-8")) == "hello"
    assert bundle.preflight_nonpdf_profile("demo.txt", b"a,b,c\n1,2,3")["profile"] in {
        "text_heavy",
        "mixed",
        "chart_heavy",
    }
    assert bundle.preflight_nonpdf_profile("demo.md", "# 图表1\n![chart](demo.png)\n趋势上升".encode("utf-8"))["profile"] in {
        "mixed",
        "chart_heavy",
    }
    assert bundle.resolve_nonpdf_budgets("mixed")["profile"] == "mixed"
    assert bundle.normalize_soft_warnings(["a", "a", "b"]) == ["a", "b"]
    assert bundle.strip_recovered_extract_warnings(
        ["quality_gate_ok", "field_extract_timeout:demo"],
        quality_ok=True,
        quick_fallback=False,
    ) == []
    promoted = bundle.promote_visual_diagnostics({"parse_stats": {"mineru_run": {"status": "ok"}}})
    assert promoted["mineru_status"] == "ok"
    assert bundle.is_recoverable_timeout_error("field_extract_timeout: demo") is True


def test_main_nonpdf_bundle_keeps_plain_text_bulletins_on_text_heavy_profile_without_real_tables() -> None:
    env_values = {
        "MODULE2_PARSE_TIMEOUT_SEC": "120",
        "MODULE2_EXTRACT_TIMEOUT_SEC": "150",
        "MODULE2_NONPDF_TOTAL_BUDGET_SEC": "90",
        "MODULE2_NONPDF_PARSE_TEXT_SEC": "24",
        "MODULE2_NONPDF_PARSE_MIXED_SEC": "34",
        "MODULE2_NONPDF_PARSE_CHART_SEC": "42",
        "MODULE2_NONPDF_PARSE_TABLE_SEC": "24",
        "MODULE2_NONPDF_EXTRACT_TEXT_SEC": "34",
        "MODULE2_NONPDF_EXTRACT_MIXED_SEC": "44",
        "MODULE2_NONPDF_EXTRACT_CHART_SEC": "52",
        "MODULE2_NONPDF_EXTRACT_TABLE_SEC": "64",
        "MODULE2_NONPDF_TOTAL_BUDGET_TABLE_SEC": "88",
    }
    bundle = main_nonpdf_bundle_module.build_module2_main_nonpdf_bundle(
        getenv=lambda name, default=None: env_values.get(name, default),
    )

    payload = (
        "2024年国民经济和社会发展统计公报\n"
        "表1反映了总体情况。\n"
        "图2显示了就业变化。\n"
        "全年国内生产总值1349084亿元，比上年增长5.0%。\n"
        "年末全国人口140828万人。\n"
    ).encode("utf-8")

    profile = bundle.preflight_nonpdf_profile("demo.txt", payload)

    assert profile["signals"]["figure_keyword_hits"] >= 2
    assert profile["signals"]["txt_table_lines"] == 0
    assert profile["signals"]["figure_cue_lines"] == 2
    assert profile["profile"] == "text_heavy"
