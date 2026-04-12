from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_quick_extract_bundle_module = import_module("module2.app.bootstrap.quick_extract")


def test_build_module2_main_quick_extract_bundle_exposes_numeric_and_table_fallback_helpers() -> None:
    bundle = main_quick_extract_bundle_module.build_module2_main_quick_extract_bundle(
        is_low_value_auto_schema_field_name=lambda field_name: str(field_name) == "ignore_me",
        coerce_field_type=lambda field_type: str(field_type.get("type") if isinstance(field_type, dict) else field_type),
        is_low_value_quick_fallback_value=lambda value: str(value).strip().lower() in {"-", "n/a"},
        normalize_bbox=lambda bbox, page_hint=None: {"bbox": bbox, "page_hint": page_hint},
    )

    assert bundle.to_number_or_none(" 1,234.5% ") == 1234.5
    assert bundle.to_number_or_none(" 1，234.5％ ") == 1234.5
    assert bundle.to_number_or_none("not-a-number") is None

    results = bundle.quick_extract_from_tables(
        table_blocks=[
            {
                "page": 2,
                "rows": [
                    {
                        "cells": [
                            {
                                "header": "Invoice Total",
                                "text": "1,288.00",
                                "numeric_value": "1288.00",
                                "ref_id": "r1",
                                "bbox": [2, 10, 20, 30, 40],
                            },
                            {
                                "header": "Customer Name",
                                "text": "Acme Corp",
                                "ref_id": "r2",
                                "bbox": [2, 11, 21, 31, 41],
                            },
                        ]
                    }
                ],
            }
        ],
        schema_fields={
            "invoice_total": {"type": "number"},
            "customer_name": {"type": "string"},
            "ignore_me": {"type": "string"},
        },
    )

    assert results["invoice_total"]["value"] == 1288.0
    assert results["invoice_total"]["source_ref_id"] == "r1"
    assert results["invoice_total"]["bbox"] == {"bbox": [2, 10, 20, 30, 40], "page_hint": 2}
    assert results["customer_name"]["value"] == "Acme Corp"
    assert "ignore_me" not in results


def test_module2_main_quick_extract_bundle_skips_low_value_non_numeric_fallbacks() -> None:
    bundle = main_quick_extract_bundle_module.build_module2_main_quick_extract_bundle(
        is_low_value_auto_schema_field_name=lambda field_name: False,
        coerce_field_type=lambda field_type: "string",
        is_low_value_quick_fallback_value=lambda value: str(value).strip().lower() in {"-", "n/a"},
        normalize_bbox=lambda bbox, page_hint=None: bbox,
    )

    results = bundle.quick_extract_from_tables(
        table_blocks=[
            {
                "page": 1,
                "rows": [
                    {"cells": [{"header": "Status", "text": "-", "bbox": [1, 1, 2, 3, 4]}]},
                ],
            }
        ],
        schema_fields={"status": {"type": "string"}},
    )

    assert results == {}
