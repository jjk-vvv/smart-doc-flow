from __future__ import annotations

import re
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_inference_bundle_module = import_module("module2.app.bootstrap.schema_inference")


def _sanitize_field_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9_ ]+", " ", text)
    return "_".join(part for part in text.split() if part)


def _build_bundle():
    return main_schema_inference_bundle_module.build_module2_main_schema_inference_bundle(
        sanitize_field_name=_sanitize_field_name,
        is_low_value_auto_schema_field_name=lambda field_name: str(field_name or "").strip().lower()
        in {
            "name",
            "page",
            "annual_health_report",
            "medical_resource_summary",
        },
        filter_auto_schema_fields=lambda fields, max_fields: dict(list(fields.items())[:max_fields]),
        schema_field_type_priority=lambda field_type: {
            "string": 0,
            "number": 1,
            "integer": 2,
            "date": 2,
            "boolean": 2,
        }.get(str(field_type or "").strip().lower(), 0),
        schema_context_clean_text=lambda value: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip(),
        looks_like_schema_figure_title=lambda candidate: str(candidate or "").strip().lower().startswith("figure"),
        looks_like_schema_sentence_fragment=lambda candidate: any(
            token in str(candidate or "").strip().lower() for token in ("shows", "indicates")
        ),
        date_field_tokens=("date", "year"),
        integer_field_tokens=("count", "quantity", "qty"),
        number_field_tokens=("amount", "total", "price", "revenue"),
        schema_heuristic_stop_tokens={"page", "ref"},
    )


def test_build_module2_main_schema_inference_bundle_infers_type_preferences_from_field_name() -> None:
    bundle = _build_bundle()

    assert bundle.field_name_prefers_date("report_date") is True
    assert bundle.field_name_prefers_integer("item_count") is True
    assert bundle.field_name_prefers_integer("report_date") is False
    assert bundle.field_name_prefers_number("invoice_total_amount") is True
    assert bundle.field_name_prefers_number("report_date") is False

    assert bundle.infer_field_type_from_name("report_date") == "date"
    assert bundle.infer_field_type_from_name("item_count") == "integer"
    assert bundle.infer_field_type_from_name("invoice_total_amount") == "number"
    assert bundle.infer_field_type_from_name("customer_name") == "string"


def test_module2_main_schema_inference_bundle_collects_candidates_from_table_figure_and_markdown() -> None:
    bundle = _build_bundle()

    out = bundle.infer_schema_fields_heuristic(
        markdown="""
        <p>Invoice Total: 1200</p>
        Customer Name: ACME
        Page: 2
        """,
        table_blocks=[
            {
                "headers": ["Invoice Total", "Item Count", "Name"],
                "header_meta": [{"name": "Revenue", "unit": "amount"}],
            }
        ],
        figure_blocks=[
            {
                "caption": "Revenue by Region",
                "key_points": ["chart shows regional change", "Net Profit"],
                "dataframe": {"headers": ["Region", "Revenue Total"]},
            }
        ],
        max_fields=10,
    )

    assert out["invoice_total"] == "number"
    assert out["item_count"] == "integer"
    assert out["revenue_total"] == "number"
    assert out["customer_name"] == "string"
    assert "name" not in out
    assert "page" not in out
    assert "chart_shows_regional_change" not in out
    assert len(out) <= 10


def test_module2_main_schema_inference_bundle_uses_markdown_key_value_hits_without_table_or_figure() -> None:
    bundle = _build_bundle()

    out = bundle.infer_schema_fields_heuristic(
        markdown="""
        Report Date: 2026-03-01
        Item Count: 4
        Customer Name: Alice
        """,
        table_blocks=[],
        figure_blocks=[],
        max_fields=4,
    )

    assert out["report_date"] == "date"
    assert out["item_count"] == "integer"
    assert out["customer_name"] == "string"


def test_module2_main_schema_inference_bundle_collects_heading_candidates_from_markdown() -> None:
    bundle = _build_bundle()

    out = bundle.infer_schema_fields_heuristic(
        markdown="""
        # Annual Health Report

        ## Medical Resource Summary

        ### Total Institution Count

        ### Total Health Expenditure
        """,
        table_blocks=[],
        figure_blocks=[],
        max_fields=6,
    )

    assert "annual_health_report" not in out
    assert "medical_resource_summary" not in out
    assert "total_institution_count" in out
    assert "total_health_expenditure" in out
