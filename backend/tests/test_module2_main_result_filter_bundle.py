from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_result_filter_bundle_module = import_module("app.modules.module2.bootstrap.result_filter")
main_schema_fields_bundle_module = import_module("app.modules.module2.bootstrap.schema_fields")


def test_build_module2_main_result_filter_bundle_detects_low_value_result_values() -> None:
    bundle = main_result_filter_bundle_module.build_module2_main_result_filter_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=lambda field_name: False,
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: short_name == "amount"
        and long_name == "invoice_amount",
        to_number_or_none=lambda value: float(str(value).replace(",", "")) if str(value).replace(",", "").replace(".", "", 1).isdigit() else None,
        auto_schema_stopwords_en={"the", "and", "of"},
        low_value_result_generic_en={"result", "summary", "generic"},
        low_value_result_generic_zh={"结果", "摘要"},
    )

    assert bundle.is_low_value_result_value("invoice_total", "invoice total") is True
    assert bundle.is_low_value_result_value("amount", "128.5") is False
    assert bundle.is_low_value_result_value("chart_note", "legend") is True
    assert bundle.is_low_value_result_value("generic", "结果") is True


def test_module2_main_result_filter_bundle_filters_and_prunes_auto_results() -> None:
    bundle = main_result_filter_bundle_module.build_module2_main_result_filter_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=lambda field_name: str(field_name) == "generic",
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: short_name == "amount"
        and long_name == "invoice_amount",
        to_number_or_none=lambda value: float(str(value).replace(",", "")) if str(value).replace(",", "").replace(".", "", 1).isdigit() else None,
        auto_schema_stopwords_en={"the", "and", "of"},
        low_value_result_generic_en={"result", "summary", "generic"},
        low_value_result_generic_zh={"结果", "摘要"},
    )

    filtered, removed = bundle.filter_low_value_auto_results(
        {
            "": {"value": "blank"},
            "generic": {"value": "Acme"},
            "broken": "oops",
            "notes": {"value": "summary"},
            "amount": {"value": "128.5"},
            "invoice_amount": {"value": "128.5"},
            "customer_name": {"value": "Acme Corp"},
        }
    )

    assert filtered == {
        "invoice_amount": {"value": "128.5"},
        "customer_name": {"value": "Acme Corp"},
    }
    assert removed[""] == "empty_field_name"
    assert removed["generic"] == "low_value_field_name"
    assert removed["broken"] == "invalid_entity"
    assert removed["notes"] == "low_value_result_value"
    assert removed["amount"] == "shadowed_by_more_specific_field:invoice_amount"


def test_module2_main_result_filter_bundle_adjusts_quality_schema_fields_without_dropping_low_value_result_targets() -> None:
    bundle = main_result_filter_bundle_module.build_module2_main_result_filter_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=lambda field_name: False,
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: False,
        to_number_or_none=lambda value: None,
        auto_schema_stopwords_en=set(),
        low_value_result_generic_en=set(),
        low_value_result_generic_zh=set(),
    )

    adjusted = bundle.effective_quality_schema_fields(
        {
            "generic": {"type": "string"},
            "amount": {"type": "number"},
            "notes": {"type": "string"},
            "customer_name": {"type": "string"},
        },
        {
            "generic": "low_value_field_name",
            "amount": "shadowed_by_more_specific_field:invoice_amount",
            "notes": "low_value_result_value",
        },
    )

    assert adjusted == {
        "notes": {"type": "string"},
        "customer_name": {"type": "string"},
    }


def test_module2_main_result_filter_bundle_drops_compact_exact_comparative_tail_fields() -> None:
    schema_fields_bundle = main_schema_fields_bundle_module.build_module2_main_schema_fields_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        coerce_field_type=lambda value: str(value or "string").strip().lower(),
        schema_field_type_priority=lambda field_type: {
            "string": 0,
            "number": 1,
            "integer": 2,
            "date": 2,
            "boolean": 2,
        }.get(str(field_type or "").strip().lower(), 0),
        schema_field_type_hint=lambda type_hint: type_hint.get("type") if isinstance(type_hint, dict) else type_hint,
        auto_schema_stopwords_en={"the", "and", "of"},
        auto_schema_generic_en={"name", "value", "result"},
        auto_schema_generic_zh={"\u540d\u79f0", "\u6570\u636e"},
        auto_schema_generic_zh_exact={"\u6bd4\u4e0a\u5e74\u589e\u957f"},
        auto_schema_generic_zh_unit_tokens={"\u5143", "\u53f0"},
        auto_schema_generic_ja_exact=set(),
    )
    bundle = main_result_filter_bundle_module.build_module2_main_result_filter_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=schema_fields_bundle.is_low_value_auto_schema_field_name,
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: False,
        to_number_or_none=lambda value: float(str(value).replace(",", "")) if str(value).replace(",", "").replace(".", "", 1).isdigit() else None,
        auto_schema_stopwords_en={"the", "and", "of"},
        low_value_result_generic_en={"result", "summary", "generic"},
        low_value_result_generic_zh={"\u7ed3\u679c", "\u6458\u8981"},
    )

    filtered, removed = bundle.filter_low_value_auto_results(
        {
            "\u6bd4 \u4e0a\u5e74\u589e\u957f": {"value": "6.2%"},
            "\u793e\u4f1a\u7ec4\u7ec7\u6350\u8d60\u6536\u5165": {"value": "128.5"},
        }
    )

    assert filtered == {
        "\u793e\u4f1a\u7ec4\u7ec7\u6350\u8d60\u6536\u5165": {"value": "128.5"},
    }
    assert removed["\u6bd4_\u4e0a\u5e74\u589e\u957f"] == "low_value_field_name"


def test_module2_main_result_filter_bundle_drops_cjk_table_title_fields() -> None:
    schema_fields_bundle = main_schema_fields_bundle_module.build_module2_main_schema_fields_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        coerce_field_type=lambda value: str(value or "string").strip().lower(),
        schema_field_type_priority=lambda field_type: {
            "string": 0,
            "number": 1,
            "integer": 2,
            "date": 2,
            "boolean": 2,
        }.get(str(field_type or "").strip().lower(), 0),
        schema_field_type_hint=lambda type_hint: type_hint.get("type") if isinstance(type_hint, dict) else type_hint,
        auto_schema_stopwords_en={"the", "and", "of"},
        auto_schema_generic_en={"name", "value", "result"},
        auto_schema_generic_zh={"\u540d\u79f0", "\u6570\u636e"},
        auto_schema_generic_zh_exact={"\u5907\u6ce8"},
        auto_schema_generic_zh_unit_tokens={"\u5143", "\u53f0"},
        auto_schema_generic_ja_exact=set(),
    )
    bundle = main_result_filter_bundle_module.build_module2_main_result_filter_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=schema_fields_bundle.is_low_value_auto_schema_field_name,
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: False,
        to_number_or_none=lambda value: float(str(value).replace(",", "")) if str(value).replace(",", "").replace(".", "", 1).isdigit() else None,
        auto_schema_stopwords_en={"the", "and", "of"},
        low_value_result_generic_en={"result", "summary", "generic"},
        low_value_result_generic_zh={"\u7ed3\u679c", "\u6458\u8981"},
    )

    filtered, removed = bundle.filter_low_value_auto_results(
        {
            "\u8868 4 2021 \u5e74\u793e\u4f1a\u7ec4\u7ec7\u6309\u767b\u8bb0\u673a\u5173\u5206\u7c7b \u5355\u4f4d": {"value": "\u4e07\u4e2a"},
            "\u793e\u4f1a\u7ec4\u7ec7\u6350\u8d60\u6536\u5165": {"value": "1192.5"},
        }
    )

    assert filtered == {
        "\u793e\u4f1a\u7ec4\u7ec7\u6350\u8d60\u6536\u5165": {"value": "1192.5"},
    }
    assert removed["\u8868_4_2021_\u5e74\u793e\u4f1a\u7ec4\u7ec7\u6309\u767b\u8bb0\u673a\u5173\u5206\u7c7b_\u5355\u4f4d"] == "low_value_field_name"
