from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_pipeline_bundle_module = import_module("module2.app.services.schema.schema_pipeline_builder")


def test_build_module2_main_schema_pipeline_bundle_exposes_expected_runtime_fields(monkeypatch) -> None:
    calls: dict[str, dict] = {}

    def _capture(name: str, marker):
        def _builder(**kwargs):
            calls[name] = dict(kwargs)
            return marker

        return _builder

    schema_context_bundle = SimpleNamespace(
        schema_context_clean_text=lambda value: f"clean:{value}",
        looks_like_schema_figure_title=lambda value: f"figure:{value}",
        looks_like_schema_sentence_fragment=lambda value: f"sentence:{value}",
        extract_text_for_schema=lambda *args, **kwargs: "schema-context",
    )
    schema_fields_bundle = SimpleNamespace(
        is_low_value_auto_schema_field_name=lambda value: f"low:{value}",
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: f"prune:{short_name}:{long_name}",
        normalize_schema_fields=lambda fields, max_fields: ("normalized", fields, max_fields),
        filter_auto_schema_fields=lambda fields, max_fields: ("filtered", fields, max_fields),
        upsert_schema_field_candidate=lambda *args, **kwargs: "upserted",
        field_name_word_tokens=lambda value: f"tokens:{value}",
    )
    result_filter_bundle = SimpleNamespace(name="result-filter")
    schema_request_bundle = SimpleNamespace(name="schema-request")
    schema_inference_bundle = SimpleNamespace(infer_schema_fields_heuristic=lambda *args, **kwargs: {"heuristic": "ok"})
    schema_llm_bundle = SimpleNamespace(infer_schema_fields_llm=lambda *args, **kwargs: {"llm": "ok"})
    schema_semantics_bundle = SimpleNamespace(
        semantic_closure_fragment_alias_keys={"amount": "invoice_total"},
        schema_semantic_label_strength=lambda value: f"strength:{value}",
        is_semantically_weak_field_label=lambda value: f"weak:{value}",
    )
    schema_selection_bundle = SimpleNamespace(
        select_best_canonical_schema_fields=lambda *args, **kwargs: ("selected", args, kwargs),
        apply_conservative_semantic_closure=lambda *args, **kwargs: ("closure", args, kwargs),
    )
    schema_resolution_bundle = SimpleNamespace(resolve_effective_schema=lambda *args, **kwargs: ("resolved", args, kwargs))
    schema_timeout_bundle = SimpleNamespace(resolve_dynamic_extract_timeout_sec=lambda *args, **kwargs: 123)

    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_context_bundle",
        _capture("schema_context", schema_context_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_fields_bundle",
        _capture("schema_fields", schema_fields_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_result_filter_bundle",
        _capture("result_filter", result_filter_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_request_bundle",
        _capture("schema_request", schema_request_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_inference_bundle",
        _capture("schema_inference", schema_inference_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_llm_bundle",
        _capture("schema_llm", schema_llm_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_semantics_bundle",
        _capture("schema_semantics", schema_semantics_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_selection_bundle",
        _capture("schema_selection", schema_selection_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_resolution_bundle",
        _capture("schema_resolution", schema_resolution_bundle),
    )
    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_timeout_bundle",
        _capture("schema_timeout", schema_timeout_bundle),
    )

    primitives_bundle = SimpleNamespace(
        sanitize_field_name=lambda value: f"sanitize:{value}",
        coerce_field_type=lambda value: f"type:{value}",
        schema_field_type_priority=lambda value: f"priority:{value}",
        schema_field_type_hint=lambda value: f"hint:{value}",
        schema_target_fields=lambda schema: f"target:{schema}",
    )
    quality_bundle = SimpleNamespace(
        count_table_cells=lambda payload: f"table-cells:{payload}",
        count_figure_dataframe_cells=lambda payload: f"figure-cells:{payload}",
    )
    quick_extract_bundle = SimpleNamespace(to_number_or_none=lambda value: f"num:{value}")

    bundle = main_schema_pipeline_bundle_module.build_module2_main_schema_pipeline_bundle(
        graph="graph-runtime",
        getenv=lambda key, default="": default,
        main_schema_primitives_bundle=primitives_bundle,
        main_quality_bundle=quality_bundle,
        main_quick_extract_bundle=quick_extract_bundle,
        normalize_field_name_fn=lambda value: f"normalize:{value}",
        canonicalize_schema_fields_fn=lambda fields, template_hint: ("canonical", fields, template_hint),
        normalize_schema_contracts_fn=lambda schema, raw_to_canonical, template_hint: {
            "schema": schema,
            "raw_to_canonical": raw_to_canonical,
            "template_hint": template_hint,
        },
        infer_rule_backed_schema_fields=lambda **kwargs: {"rules": "ok"},
        is_word_file=lambda file_name: file_name.endswith(".docx"),
        schema_noise_rules={"schema_heuristic_stop_tokens": {"skip-this"}},
        schema_semantic_rules={"rules": "semantic"},
        schema_selection_rules={"rules": "selection"},
        schema_coverage_profiles={"templates": {"finance_document": {"critical_fields": ("customer_name",)}}},
        auto_schema_stopwords_en={"stop"},
        auto_schema_generic_en={"generic-en"},
        auto_schema_generic_zh={"generic-zh"},
        auto_schema_generic_zh_exact={"generic-zh-exact"},
        auto_schema_generic_zh_unit_tokens={"unit-zh"},
        auto_schema_generic_ja_exact={"generic-ja-exact"},
        low_value_result_generic_en={"low-en"},
        low_value_result_generic_zh={"low-zh"},
        schema_figure_title_tokens=("figure-title",),
        schema_sentence_cue_tokens_zh=("cue-zh",),
        schema_sentence_cue_tokens_en=("cue-en",),
        date_field_tokens=("date",),
        integer_field_tokens=("integer",),
        number_field_tokens=("number",),
    )

    assert bundle.result_filter_bundle is result_filter_bundle
    assert bundle.schema_context_bundle is schema_context_bundle
    assert bundle.schema_fields_bundle is schema_fields_bundle
    assert bundle.schema_request_bundle is schema_request_bundle
    assert bundle.schema_inference_bundle is schema_inference_bundle
    assert bundle.schema_llm_bundle is schema_llm_bundle
    assert bundle.schema_semantics_bundle is schema_semantics_bundle
    assert bundle.schema_selection_bundle is schema_selection_bundle
    assert bundle.schema_resolution_bundle is schema_resolution_bundle
    assert bundle.schema_timeout_bundle is schema_timeout_bundle

    assert calls["schema_context"]["schema_figure_title_tokens"] == ("figure-title",)
    assert calls["schema_fields"]["auto_schema_generic_zh_unit_tokens"] == {"unit-zh"}
    assert calls["result_filter"]["is_low_value_auto_schema_field_name"]("amount") == "low:amount"
    assert calls["result_filter"]["should_prune_shadowed_auto_field_name"]("a", "amount") == "prune:a:amount"
    assert calls["schema_request"]["normalize_schema_fields"]({"Invoice Total": "number"}, 3) == (
        "normalized",
        {"Invoice Total": "number"},
        3,
    )
    assert calls["schema_inference"]["schema_context_clean_text"]("demo") == "clean:demo"
    assert calls["schema_selection"]["normalize_field_name_fn"]("Invoice Total") == "normalize:Invoice Total"
    assert calls["schema_selection"]["schema_coverage_profiles"] == {
        "templates": {"finance_document": {"critical_fields": ("customer_name",)}}
    }
    assert calls["schema_resolution"]["schema_coverage_profiles"] == {
        "templates": {"finance_document": {"critical_fields": ("customer_name",)}}
    }
    assert calls["schema_timeout"]["is_word_file"]("demo.docx") is True


def test_build_module2_main_schema_pipeline_bundle_from_rules_uses_asset_payloads(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return "pipeline-bundle"

    monkeypatch.setattr(
        main_schema_pipeline_bundle_module,
        "build_module2_main_schema_pipeline_bundle",
        fake_builder,
    )

    bundle = main_schema_pipeline_bundle_module.build_module2_main_schema_pipeline_bundle_from_rules(
        graph="graph-runtime",
        getenv=lambda key, default="": default,
        main_schema_primitives_bundle="primitives",
        main_quality_bundle="quality",
        main_quick_extract_bundle="quick",
        normalize_field_name_fn="normalize",
        canonicalize_schema_fields_fn="canonical",
        normalize_schema_contracts_fn="contracts",
        infer_rule_backed_schema_fields="infer-rules",
        is_word_file="is-word",
        schema_noise_rules={
            "auto_schema_stopwords_en": frozenset({"the", "of"}),
            "auto_schema_generic_en": frozenset({"generic-en"}),
            "auto_schema_generic_zh": frozenset({"通用字段"}),
            "auto_schema_generic_zh_exact": frozenset({"备注"}),
            "auto_schema_generic_zh_unit_tokens": frozenset({"万元"}),
            "auto_schema_generic_ja_exact": frozenset({"設備名"}),
            "low_value_result_generic_en": frozenset({"summary"}),
            "low_value_result_generic_zh": frozenset({"摘要"}),
        },
        schema_semantic_rules={"semantic": "rules"},
        schema_selection_rules={"selection": "rules"},
        schema_coverage_profiles={"templates": {"finance_document": {"critical_fields": ("customer_name",)}}},
        field_type_rules={
            "date_tokens": ("日期", "date"),
            "integer_tokens": ("数量", "count"),
            "number_tokens": ("金额", "amount"),
        },
    )

    assert bundle == "pipeline-bundle"
    assert captured["auto_schema_stopwords_en"] == {"the", "of"}
    assert captured["auto_schema_generic_en"] == {"generic-en"}
    assert captured["auto_schema_generic_zh"] == {"通用字段"}
    assert captured["low_value_result_generic_zh"] == {"摘要"}
    assert captured["date_field_tokens"] == ("日期", "date")
    assert captured["integer_field_tokens"] == ("数量", "count")
    assert captured["number_field_tokens"] == ("金额", "amount")
    assert captured["schema_coverage_profiles"] == {
        "templates": {"finance_document": {"critical_fields": ("customer_name",)}}
    }
    assert "示意图" in captured["schema_figure_title_tokens"]
