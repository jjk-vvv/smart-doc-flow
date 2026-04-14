from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_fields_bundle_module = import_module("app.modules.module2.bootstrap.schema_fields")


def _build_bundle():
    return main_schema_fields_bundle_module.build_module2_main_schema_fields_bundle(
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
        auto_schema_generic_zh_exact={"\u5907\u6ce8", "\u6bd4\u4e0a\u5e74\u589e\u957f"},
        auto_schema_generic_zh_unit_tokens={"\u5143", "\u53f0"},
        auto_schema_generic_ja_exact={"\u540d\u79f0"},
    )


def test_build_module2_main_schema_fields_bundle_identifies_low_value_field_names() -> None:
    bundle = _build_bundle()

    assert bundle.is_low_value_auto_schema_field_name("name") is True
    assert bundle.is_low_value_auto_schema_field_name("table 1") is True
    assert bundle.is_low_value_auto_schema_field_name("annual_health_report") is True
    assert bundle.is_low_value_auto_schema_field_name("medical_resource_summary") is True
    assert bundle.is_low_value_auto_schema_field_name("\u536b\u751f\u8d44\u6e90") is True
    assert bundle.is_low_value_auto_schema_field_name("\u6bd4 \u4e0a\u5e74\u589e\u957f") is True
    assert bundle.is_low_value_auto_schema_field_name(
        "\u8868 4 2021 \u5e74\u793e\u4f1a\u7ec4\u7ec7\u6309\u767b\u8bb0\u673a\u5173\u5206\u7c7b \u5355\u4f4d"
    ) is True
    assert bundle.is_low_value_auto_schema_field_name(
        "\u533b\u9662\u533b\u5e08\u5de5\u4f5c\u60c5\u51b5"
    ) is True
    assert bundle.is_low_value_auto_schema_field_name(
        "2024\u5e74\u6211\u56fd\u536b\u751f\u5065\u5eb7\u4e8b\u4e1a\u53d1\u5c55\u7edf\u8ba1\u516c\u62a5"
    ) is True
    assert bundle.is_low_value_auto_schema_field_name("\u8868\u9762\u79ef") is False
    assert bundle.is_low_value_auto_schema_field_name("invoice_total") is False
    assert bundle.is_low_value_auto_schema_field_name("total_health_expenditure") is False
    assert bundle.is_low_value_auto_schema_field_name("\u95e8\u8bca\u548c\u4f4f\u9662\u91cf") is False
    assert bundle.is_low_value_auto_schema_field_name("\u5ba2\u6237\u6570\u91cf") is False


def test_module2_main_schema_fields_bundle_upserts_and_prunes_shadowed_candidates() -> None:
    bundle = _build_bundle()

    out: dict[str, str] = {}
    bundle.upsert_schema_field_candidate(out, "Amount", "string", skip_low_value=True)
    bundle.upsert_schema_field_candidate(out, "amount", "number", skip_low_value=True)
    bundle.upsert_schema_field_candidate(out, "invoice_amount", "number", skip_low_value=True)
    bundle.upsert_schema_field_candidate(out, "table 1", "string", skip_low_value=True)

    assert out == {
        "amount": "number",
        "invoice_amount": "number",
    }

    filtered = bundle.filter_auto_schema_fields(
        {
            "amount": "number",
            "invoice_amount": "number",
            "customer_name": "string",
        },
        max_fields=5,
    )

    assert filtered == {
        "invoice_amount": "number",
        "customer_name": "string",
    }


def test_module2_main_schema_fields_bundle_normalizes_schema_fields_with_type_hints() -> None:
    bundle = _build_bundle()

    normalized = bundle.normalize_schema_fields(
        {
            "Invoice Total": {"type": "number"},
            "Invoice Total ": {"type": "integer"},
            "Date": {"type": "date"},
            "Result": {"type": "string"},
        },
        max_fields=8,
    )

    assert normalized == {
        "invoice_total": "integer",
        "date": "date",
        "result": "string",
    }


def test_module2_main_schema_fields_bundle_accepts_legacy_positional_skip_low_value() -> None:
    bundle = _build_bundle()

    out: dict[str, str] = {}
    bundle.upsert_schema_field_candidate(out, "invoice_total", "number", True)
    bundle.upsert_schema_field_candidate(out, "table 1", "string", True)

    assert out == {
        "invoice_total": "number",
    }
