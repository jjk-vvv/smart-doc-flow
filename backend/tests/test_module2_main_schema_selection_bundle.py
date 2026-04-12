from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_selection_bundle_module = import_module("module2.app.bootstrap.schema_selection")


def _build_bundle(*, schema_coverage_profiles=None):
    return main_schema_selection_bundle_module.build_module2_main_schema_selection_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        is_low_value_auto_schema_field_name=lambda field_name: str(field_name) in {"generic", "chart"},
        semantic_closure_fragment_alias_keys=lambda field_meta: {
            str(field_meta.get("unit_norm") or "").strip().lower()
        }
        if str(field_meta.get("unit_norm") or "").strip()
        else set(),
        schema_semantic_label_strength=lambda field_name, field_type, field_meta: {
            "amount": 6,
            "invoice_total_amount": 22,
            "customer_name": 18,
            "generic": -5,
        }.get(str(field_name or "").strip().lower(), 8),
        is_semantically_weak_field_label=lambda label: str(label or "").strip().lower() == "amount",
        normalize_field_name_fn=lambda source_text, **kwargs: {
            "canonical_label": "invoice_total_amount"
            if "invoice" in str(source_text or "").lower()
            else str(source_text or "").strip().lower().replace(" ", "_"),
            "canonical_base_label": "invoice_total_amount"
            if "invoice" in str(source_text or "").lower()
            else str(source_text or "").strip().lower().replace(" ", "_"),
            "unit_norm": "usd" if "invoice" in str(source_text or "").lower() else "",
            "unit_raw": "USD" if "invoice" in str(source_text or "").lower() else "",
            "dimensions": {},
            "normalization_rule_id": "finance.amount" if "invoice" in str(source_text or "").lower() else "",
            "normalization_confidence": 0.86 if "invoice" in str(source_text or "").lower() else 0.0,
        },
        coerce_field_type=lambda value: str(value or "string").strip().lower(),
        schema_semantic_rules={
            "closure_min_score": 8,
            "closure_min_gain": 8,
            "closure_min_unique_gap": 3,
        },
        schema_coverage_profiles=schema_coverage_profiles,
    )


def test_module2_main_schema_selection_bundle_applies_conservative_semantic_closure() -> None:
    bundle = _build_bundle()

    candidate = bundle.pick_semantic_closure_candidate(
        "amount",
        "number",
        {
            "raw_names": ["Invoice Total Amount"],
            "aliases": ["usd"],
            "unit_norm": "usd",
        },
        template_hint="finance_document",
    )

    assert candidate is not None
    assert candidate["label"] == "invoice_total_amount"

    (
        next_fields,
        next_meta,
        next_raw_to_canonical,
        next_canonical_to_raw,
        stats,
    ) = bundle.apply_conservative_semantic_closure(
        {"amount": "number", "customer_name": "string"},
        {
            "amount": {"raw_names": ["Invoice Total Amount"], "aliases": ["usd"], "unit_norm": "usd"},
            "customer_name": {"raw_names": ["Customer Name"]},
        },
        {"Invoice Total Amount": "amount", "Customer Name": "customer_name"},
        {"amount": "Invoice Total Amount", "customer_name": "Customer Name"},
        template_hint="finance_document",
    )

    assert next_fields == {
        "invoice_total_amount": "number",
        "customer_name": "string",
    }
    assert next_meta["invoice_total_amount"]["semantic_closure_source"] == "raw"
    assert next_raw_to_canonical["Invoice Total Amount"] == "invoice_total_amount"
    assert next_canonical_to_raw["invoice_total_amount"] == "Invoice Total Amount"
    assert stats == {
        "semantic_closure_renamed_count": 1,
        "semantic_closure_fields": {"amount": "invoice_total_amount"},
    }


def test_module2_main_schema_selection_bundle_selects_best_canonical_fields() -> None:
    bundle = _build_bundle()

    score_strong = bundle.schema_field_selection_score(
        "invoice_total_amount",
        "number",
        {"normalization_rule_id": "finance.amount", "normalization_confidence": 0.86, "unit_norm": "usd"},
        template_hint="finance_document",
    )
    score_weak = bundle.schema_field_selection_score(
        "generic",
        "string",
        {},
        template_hint="finance_document",
    )

    assert score_strong > score_weak

    selected_fields, selected_meta = bundle.select_best_canonical_schema_fields(
        {
            "invoice_total_amount": "number",
            "customer_name": "string",
            "generic": "string",
        },
        {
            "invoice_total_amount": {"normalization_rule_id": "finance.amount", "normalization_confidence": 0.86},
            "customer_name": {"normalization_confidence": 0.4},
            "generic": {},
        },
        max_fields=2,
        template_hint="finance_document",
    )

    assert selected_fields == {
        "invoice_total_amount": "number",
        "customer_name": "string",
    }
    assert set(selected_meta.keys()) == {"invoice_total_amount", "customer_name"}


def test_module2_main_schema_selection_bundle_prioritizes_critical_fields_from_coverage_profile() -> None:
    bundle = _build_bundle(
        schema_coverage_profiles={
            "templates": {
                "finance_document": {
                    "critical_fields": ("customer_name",),
                    "preferred_fields": ("invoice_total_amount",),
                }
            }
        }
    )

    selected_fields, selected_meta = bundle.select_best_canonical_schema_fields(
        {
            "invoice_total_amount": "number",
            "customer_name": "string",
            "generic": "string",
        },
        {
            "invoice_total_amount": {"normalization_rule_id": "finance.amount", "normalization_confidence": 0.86},
            "customer_name": {"normalization_confidence": 0.1},
            "generic": {},
        },
        max_fields=1,
        template_hint="finance_document",
    )

    assert selected_fields == {"customer_name": "string"}
    assert set(selected_meta.keys()) == {"customer_name"}
