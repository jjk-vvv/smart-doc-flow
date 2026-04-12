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


post_parse_quality_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_postprocess_runtime.py"],
    "_smart_doc_flow_module2_post_parse_quality_runtime",
)

PostParseQualityRuntime = post_parse_quality_runtime_module.PostParseQualityRuntime


def test_post_parse_quality_runtime_handles_quick_fallback_and_recoverable_errors() -> None:
    runtime = PostParseQualityRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_QUICK_FALLBACK_MIN_CONF": "0.70",
            "MODULE2_MIN_COVERAGE_RATIO": "0.80",
            "MODULE2_MIN_AVG_CONFIDENCE": "0.90",
        }.get(key, default)
    )

    outcome = runtime.process(
        final_state={
            "results": {
                "invoice_total": {"value": 128.5, "confidence": 0.82, "source_ref_id": "r1"},
                "generic": {"value": "noise", "confidence": 0.92},
                "low_conf": {"value": "kept?", "confidence": 0.55},
                "bad_entity": "oops",
            },
            "errors": ["table_extract_timeout:gemini"],
            "soft_warnings": ["seed"],
        },
        file_name="demo.pdf",
        parse_warning="parse_warning",
        nonpdf_total_budget_sec=1.0,
        total_ms=1500,
        used_quick_fallback=True,
        schema_meta={"mode": "auto"},
        effective_schema_fields={"invoice_total": {}, "generic": {}},
        normalize_soft_warnings=lambda value: [str(item) for item in value if str(item).strip()],
        is_low_value_auto_schema_field_name=lambda field_name: str(field_name) == "generic",
        has_meaningful_value=lambda value: value not in {None, "", "noise"},
        is_low_value_quick_fallback_value=lambda value: str(value) == "noise",
        is_recoverable_timeout_error=lambda message: "timeout" in str(message),
        filter_low_value_auto_results=lambda results: (results, {}),
        effective_quality_schema_fields=lambda schema_fields, removed: dict(schema_fields),
        result_quality_snapshot=lambda results, schema_fields: {
            "target_fields": len(schema_fields),
            "filled_fields": len(results),
            "coverage_ratio": 0.5,
            "avg_confidence": 0.82,
        },
        strip_recovered_extract_warnings=lambda warnings, **kwargs: list(warnings),
    )

    assert outcome.final_results == {"invoice_total": {"value": 128.5, "confidence": 0.82, "source_ref_id": "r1"}}
    assert outcome.final_errors == []
    assert outcome.semantic_removed == {}
    assert outcome.quality_schema_fields == {"invoice_total": {}, "generic": {}}
    assert outcome.degraded_reasons == ["low_coverage:0.500", "low_confidence:0.820", "quick_fallback"]
    assert outcome.business_extraction_status == "nonempty"
    assert "quick_table_fallback_filtered:3" in outcome.soft_warnings
    assert "quick_table_fallback_used:demo.pdf" in outcome.soft_warnings
    assert "downgraded:table_extract_timeout:gemini" in outcome.soft_warnings
    assert "nonpdf_budget_exceeded:500" in outcome.soft_warnings
    assert "quality_gate_degraded:low_coverage:0.500|low_confidence:0.820|quick_fallback" in outcome.soft_warnings


def test_post_parse_quality_runtime_strips_recovered_noise_when_quality_is_ok() -> None:
    runtime = PostParseQualityRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_MIN_COVERAGE_RATIO": "0.35",
            "MODULE2_MIN_AVG_CONFIDENCE": "0.55",
        }.get(key, default)
    )

    def _strip_recovered_extract_warnings(warnings, *, quality_ok: bool, quick_fallback: bool):
        assert quality_ok is True
        assert quick_fallback is False
        return [
            item
            for item in warnings
            if item not in {"quality_gate_ok", "field_extract_timeout:llm", "auto_result_filter_removed:1"}
        ]

    outcome = runtime.process(
        final_state={
            "results": {
                "kept": {"value": "A Corp", "confidence": 0.91, "source_ref_id": "r2"},
                "generic": {"value": "same as label", "confidence": 0.7},
            },
            "errors": ["field_extract_timeout:llm"],
            "soft_warnings": ["field_extract_timeout:llm"],
        },
        file_name="report.docx",
        parse_warning="",
        nonpdf_total_budget_sec=None,
        total_ms=500,
        used_quick_fallback=False,
        schema_meta={"mode": "auto"},
        effective_schema_fields={"kept": {}, "generic": {}},
        normalize_soft_warnings=lambda value: list(dict.fromkeys(str(item) for item in value if str(item).strip())),
        is_low_value_auto_schema_field_name=lambda field_name: False,
        has_meaningful_value=lambda value: bool(str(value).strip()),
        is_low_value_quick_fallback_value=lambda value: False,
        is_recoverable_timeout_error=lambda message: "timeout" in str(message),
        filter_low_value_auto_results=lambda results: (
            {"kept": results["kept"]},
            {"generic": "low_value_field_name"},
        ),
        effective_quality_schema_fields=lambda schema_fields, removed: {
            key: value
            for key, value in schema_fields.items()
            if key not in removed
        },
        result_quality_snapshot=lambda results, schema_fields: {
            "target_fields": len(schema_fields),
            "filled_fields": len(results),
            "coverage_ratio": 1.0,
            "avg_confidence": 0.91,
        },
        strip_recovered_extract_warnings=_strip_recovered_extract_warnings,
    )

    assert outcome.final_results == {"kept": {"value": "A Corp", "confidence": 0.91, "source_ref_id": "r2"}}
    assert outcome.final_errors == []
    assert outcome.semantic_removed == {"generic": "low_value_field_name"}
    assert outcome.quality_schema_fields == {"kept": {}}
    assert outcome.quality_snapshot["coverage_ratio"] == 1.0
    assert outcome.degraded_reasons == []
    assert outcome.business_extraction_status == "nonempty"
    assert outcome.soft_warnings == ["downgraded:field_extract_timeout:llm"]
