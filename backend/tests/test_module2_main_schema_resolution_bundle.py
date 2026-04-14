from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_resolution_bundle_module = import_module("app.modules.module2.bootstrap.schema_resolution")


def _sanitize_field_name(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("/", " ").split())


def _coerce_field_type(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("type")
    text = str(value or "string").strip().lower()
    return text if text in {"string", "number", "integer", "date", "boolean"} else "string"


def _normalize_schema_fields(fields: dict[str, object], max_fields: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, type_hint in list(fields.items())[:max_fields]:
        key = _sanitize_field_name(name)
        if not key:
            continue
        out[key] = _coerce_field_type(type_hint)
    return out


def _canonicalize_schema_fields(fields: dict[str, object], template_hint: str):
    canonical_fields = _normalize_schema_fields(fields, max_fields=max(len(fields), 1))
    field_meta = {name: {"template_hint": template_hint, "raw_names": [name]} for name in canonical_fields}
    raw_to_canonical = {_sanitize_field_name(name): _sanitize_field_name(name) for name in fields}
    canonical_to_raw = {_sanitize_field_name(name): _sanitize_field_name(name) for name in fields}
    naming_stats = {"template_hint": template_hint}
    return canonical_fields, field_meta, raw_to_canonical, canonical_to_raw, naming_stats


def _select_best_canonical_schema_fields(
    canonical_fields: dict[str, object],
    field_meta: dict[str, object],
    max_fields: int,
    template_hint: str,
):
    keys = list(canonical_fields.keys())[:max_fields]
    return {key: canonical_fields[key] for key in keys}, {key: field_meta[key] for key in keys}


def _apply_conservative_semantic_closure(
    canonical_fields: dict[str, object],
    field_meta: dict[str, object],
    raw_to_canonical: dict[str, str],
    canonical_to_raw: dict[str, str],
    template_hint: str,
):
    next_fields = dict(canonical_fields)
    next_meta = dict(field_meta)
    next_raw_to_canonical = dict(raw_to_canonical)
    next_canonical_to_raw = dict(canonical_to_raw)
    stats = {"semantic_closure_renamed_count": 0}
    if "amount" in next_fields:
        next_fields["invoice_total"] = next_fields.pop("amount")
        next_meta["invoice_total"] = {"template_hint": template_hint, "semantic_closure_source": "raw"}
        next_meta.pop("amount", None)
        for raw_name, canonical_name in list(next_raw_to_canonical.items()):
            if canonical_name == "amount":
                next_raw_to_canonical[raw_name] = "invoice_total"
        next_canonical_to_raw.pop("amount", None)
        next_canonical_to_raw["invoice_total"] = "amount"
        stats = {
            "semantic_closure_renamed_count": 1,
            "semantic_closure_fields": {"amount": "invoice_total"},
        }
    return next_fields, next_meta, next_raw_to_canonical, next_canonical_to_raw, stats


def _upsert_schema_field_candidate(out: dict[str, str], field_name: object, field_type: object, skip_low_value: bool) -> None:
    key = _sanitize_field_name(field_name)
    if not key:
        return
    if skip_low_value and key in {"page", "name"}:
        return
    out[key] = _coerce_field_type(field_type)


def _filter_auto_schema_fields(fields: dict[str, str], max_fields: int) -> dict[str, str]:
    return dict(list(fields.items())[:max_fields])


def _normalize_schema_contracts(schema: dict[str, object], raw_to_canonical: dict[str, str], template_hint: str):
    required = [
        raw_to_canonical.get(_sanitize_field_name(name), _sanitize_field_name(name))
        for name in schema.get("required", [])
        if _sanitize_field_name(name)
    ]
    return {
        "required": required,
        "template_hint": template_hint,
        "fields": dict(schema.get("fields", {})),
    }


def _build_bundle(*, llm_fields=None, rule_fields=None, heuristic_fields=None, schema_coverage_profiles=None):
    async def _infer_schema_fields_llm(file_name, markdown, table_blocks, figure_blocks, max_fields):
        return dict(llm_fields or {})

    def _infer_rule_backed_schema_fields(**kwargs):
        return dict(rule_fields or {})

    def _infer_schema_fields_heuristic(markdown, table_blocks, figure_blocks, max_fields):
        return dict(heuristic_fields or {})

    return main_schema_resolution_bundle_module.build_module2_main_schema_resolution_bundle(
        schema_target_fields=lambda schema: dict(schema.get("fields") or {}) if isinstance(schema, dict) else {},
        normalize_schema_fields=_normalize_schema_fields,
        select_best_canonical_schema_fields=_select_best_canonical_schema_fields,
        apply_conservative_semantic_closure=_apply_conservative_semantic_closure,
        upsert_schema_field_candidate=_upsert_schema_field_candidate,
        filter_auto_schema_fields=_filter_auto_schema_fields,
        infer_schema_fields_llm=_infer_schema_fields_llm,
        infer_rule_backed_schema_fields=_infer_rule_backed_schema_fields,
        infer_schema_fields_heuristic=_infer_schema_fields_heuristic,
        canonicalize_schema_fields_fn=_canonicalize_schema_fields,
        normalize_schema_contracts_fn=_normalize_schema_contracts,
        schema_selection_rules={
            "pdf_max_fields_default": 8,
            "candidate_pool_multiplier": 3,
            "candidate_pool_extra_cap": 10,
            "candidate_pool_max": 36,
            "rule_candidate_templates": ("finance_document",),
        },
        schema_coverage_profiles=schema_coverage_profiles,
        getenv=lambda key, default="": default,
    )


def test_build_module2_main_schema_resolution_bundle_support_helpers_behave_as_expected() -> None:
    bundle = _build_bundle()

    assert bundle.schema_auto_infer_requested({"auto_infer": True}) is True
    assert bundle.schema_auto_infer_requested({"fields": {"Invoice Total": "number"}}) is False
    assert bundle.schema_required_from_field_specs(
        {
            "fields": {
                "Invoice Total": {"type": "number", "required": True},
                "Customer Name": {"type": "string"},
            }
        }
    ) == ["Invoice Total"]
    assert bundle.merge_required_field_names(["Customer Name"], ["invoice total", "Customer Name"]) == [
        "Customer Name",
        "invoice total",
    ]


def test_module2_main_schema_resolution_bundle_resolves_manual_schema_without_auto_infer() -> None:
    bundle = _build_bundle()

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "fields": {
                    "Invoice Total": {"type": "number", "required": True},
                    "Customer Name": "string",
                },
                "required": ["Customer Name"],
                "max_auto_fields": 10,
            },
            file_name="invoice.pdf",
            markdown="Invoice Total: 1000",
            table_blocks=[],
            figure_blocks=[],
            profile_hint="mixed",
            naming_template="finance_document",
            allow_llm=True,
        )
    )

    assert effective["fields"] == {
        "invoice_total": "number",
        "customer_name": "string",
    }
    assert set(effective["required"]) == {"invoice_total", "customer_name"}
    assert meta["mode"] == "manual"
    assert meta["source"] == "request"
    assert meta["field_count"] == 2
    assert meta["naming_template"] == "finance_document"


def test_module2_main_schema_resolution_bundle_resolves_auto_schema_with_rules_llm_and_heuristic() -> None:
    bundle = _build_bundle(
        llm_fields={"Customer Name": "string"},
        rule_fields={"Amount": "number"},
        heuristic_fields={"Report Date": "date"},
    )

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "auto_infer": True,
                "prefer_llm": True,
                "max_auto_fields": 10,
            },
            file_name="invoice.pdf",
            markdown="Invoice Total: 1000",
            table_blocks=[],
            figure_blocks=[],
            profile_hint="mixed",
            naming_template="finance_document",
            allow_llm=True,
        )
    )

    assert effective["fields"] == {
        "invoice_total": "number",
        "customer_name": "string",
        "report_date": "date",
    }
    assert meta["mode"] == "auto"
    assert meta["source"] == "rules+llm+heuristic"
    assert meta["llm_attempted"] is True
    assert meta["llm_used"] is True
    assert meta["field_count"] == 3
    assert meta["naming_stats"]["semantic_closure_renamed_count"] == 1


def test_module2_main_schema_resolution_bundle_falls_back_to_requested_fields_when_auto_sources_are_empty() -> None:
    bundle = _build_bundle()

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "auto_infer": True,
                "fields": {"Fallback Date": "date"},
                "max_auto_fields": 6,
            },
            file_name="notes.txt",
            markdown="No strong schema clues",
            table_blocks=[],
            figure_blocks=[],
            profile_hint="mixed",
            naming_template="common_document",
            allow_llm=False,
        )
    )

    assert effective["fields"] == {"fallback_date": "date"}
    assert meta["mode"] == "auto"
    assert meta["source"] == "empty"


def test_module2_main_schema_resolution_bundle_prefers_deterministic_plain_text_schema_before_llm() -> None:
    bundle = _build_bundle(
        llm_fields={"Late Llm Field": "string"},
        rule_fields={
            "Report Title": "string",
            "Publish Agency": "string",
            "Publish Date": "date",
            "Gross Domestic Product": "number",
        },
        heuristic_fields={"Import Export Total": "number"},
    )

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "auto_infer": True,
                "prefer_llm": True,
                "max_auto_fields": 6,
            },
            file_name="report.txt",
            markdown="Gross Domestic Product: 100",
            table_blocks=[],
            figure_blocks=[],
            profile_hint="mixed",
            naming_template="finance_document",
            allow_llm=True,
        )
    )

    assert meta["mode"] == "auto"
    assert meta["source"] == "rules+heuristic"
    assert meta["llm_attempted"] is False
    assert meta["llm_used"] is False
    assert meta["rule_field_count"] == 4
    assert meta["heuristic_field_count"] == 1
    assert meta["deterministic_field_count"] == 5
    assert "late_llm_field" not in effective["fields"]


def test_module2_main_schema_resolution_bundle_raises_table_field_budget_from_coverage_profile() -> None:
    bundle = _build_bundle(
        rule_fields={
            "Visit ID": "string",
            "Patient ID": "string",
            "Gender": "string",
            "Age": "integer",
            "Weight": "number",
            "Hospital Stay Days": "integer",
            "Diagnosis Count": "integer",
            "Glucose Max": "number",
            "HbA1c": "number",
        },
        heuristic_fields={},
        schema_coverage_profiles={
            "templates": {
                "finance_document": {
                    "table_target_fields": 9,
                    "freeze_rule_field_count": 6,
                }
            }
        },
    )

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "auto_infer": True,
                "prefer_llm": False,
                "max_auto_fields": 6,
            },
            file_name="clinical.xlsx",
            markdown="",
            table_blocks=[{"source": "xlsx"}],
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template="finance_document",
            allow_llm=False,
        )
    )

    assert meta["coverage_target_fields"] == 9
    assert meta["rule_field_count"] == 9
    assert meta["field_count"] == 9
    assert len(effective["fields"]) == 9


def test_module2_main_schema_resolution_bundle_freezes_plain_text_heuristics_when_rule_coverage_is_sufficient() -> None:
    bundle = _build_bundle(
        llm_fields={"Late Llm Field": "string"},
        rule_fields={
            "Report Title": "string",
            "Publish Agency": "string",
            "Publish Date": "date",
            "Gross Domestic Product": "number",
        },
        heuristic_fields={"Import Export Total": "number"},
        schema_coverage_profiles={
            "templates": {
                "finance_document": {
                    "text_target_fields": 6,
                    "freeze_rule_field_count": 4,
                }
            }
        },
    )

    effective, meta = asyncio.run(
        bundle.resolve_effective_schema(
            requested_schema={
                "auto_infer": True,
                "prefer_llm": True,
                "max_auto_fields": 6,
            },
            file_name="report.txt",
            markdown="Gross Domestic Product: 100",
            table_blocks=[],
            figure_blocks=[],
            profile_hint="text_heavy",
            naming_template="finance_document",
            allow_llm=True,
        )
    )

    assert meta["coverage_target_fields"] == 6
    assert meta["heuristic_field_count"] == 0
    assert meta["llm_attempted"] is False
    assert meta["llm_used"] is False
    assert "import_export_total" not in effective["fields"]
