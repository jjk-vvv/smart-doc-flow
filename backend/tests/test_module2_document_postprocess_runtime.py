from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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


document_postprocess_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_postprocess_runtime.py"],
    "_smart_doc_flow_module2_document_postprocess_runtime",
)

DocumentPostprocessRuntime = document_postprocess_runtime_module.DocumentPostprocessRuntime
DocumentPostprocessDependencyBundle = document_postprocess_runtime_module.DocumentPostprocessDependencyBundle


class _QualityRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def process(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            final_results={"amount": {"value": 100}},
            final_errors=["warning"],
            soft_warnings=["quality-warning"],
            semantic_removed={"generic": "low_value"},
            quality_schema_fields={"amount": {"type": "number"}},
            quality_snapshot={"coverage_ratio": 1.0, "avg_confidence": 0.92},
            degraded_reasons=[],
            business_extraction_status="nonempty",
        )


class _ArtifactRuntime:
    def __init__(self) -> None:
        self.build_calls: list[dict[str, object]] = []
        self.enrich_calls: list[dict[str, object]] = []

    def build_context(self, **kwargs):
        self.build_calls.append(dict(kwargs))
        return SimpleNamespace(
            soft_warnings=["artifact-warning"],
            conversion_diag={"pdf_preview_url": "/extract/artifact/preview.pdf"},
            trace_hits=[{"object_type": "field"}],
            trace_stats={"trace_hit_count": 1},
            polymorphic_links=[{"field": "amount", "ref_id": "r1"}],
        )

    def enrich_diagnostics(self, **kwargs):
        self.enrich_calls.append(dict(kwargs))
        return {"seed": True, "enriched": True}


class _DiagnosticsRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_contract={"status": "success"},
            business_extraction_contract={"status": "nonempty"},
            diagnostics={"seed": True},
        )


class _ResponseRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_bundle(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(response="response-obj", cache_payload={"cache_key": kwargs["cache_key"]})


def _build_runtime(**overrides):
    defaults = dict(
        post_parse_quality_runtime=_QualityRuntime(),
        post_parse_artifact_runtime=_ArtifactRuntime(),
        diagnostics_builder_runtime=_DiagnosticsRuntime(),
        extraction_response_runtime=_ResponseRuntime(),
        graph_diagnostics_factory=lambda: {"prompt_version": "v1"},
        is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
        current_extraction_logic_version=lambda: "logic-v1",
        current_extraction_logic_components=lambda: {"fingerprint": "abc123"},
        field_naming_version="naming-v1",
        schema_rule_versions={"selection": "20260323"},
        normalize_soft_warnings=lambda value: value,
        is_low_value_auto_schema_field_name=lambda value: False,
        has_meaningful_value=lambda value: True,
        is_low_value_quick_fallback_value=lambda value: False,
        is_recoverable_timeout_error=lambda value: False,
        filter_low_value_auto_results=lambda results: (results, {}),
        effective_quality_schema_fields=lambda schema_fields, removed: schema_fields,
        result_quality_snapshot=lambda results, schema_fields: {"coverage_ratio": 1.0},
        strip_recovered_extract_warnings=lambda warnings, **kwargs: warnings,
        write_artifact_bytes=lambda **kwargs: ("frag", "/artifact"),
        build_document_trace_hits=lambda **kwargs: [],
        trace_stats_builder=lambda hits: {"trace_hit_count": len(hits)},
        build_polymorphic_links=lambda **kwargs: [],
        count_table_cells=lambda table_blocks: 0,
        table_quality_avg=lambda table_blocks: 0.0,
        table_source_counts=lambda table_blocks: {},
        count_figure_dataframe_cells=lambda figure_blocks: 0,
        figure_pages=lambda figure_blocks: [],
        figure_source_counts=lambda figure_blocks: {},
        persist_assistant1_source_markdown_artifact=lambda **kwargs: ("", "", "", ""),
        persist_assistant_payload_artifact=lambda **kwargs: ("", ""),
        promote_visual_diagnostics=lambda payload: payload,
        extraction_result_factory=lambda payload: payload,
        document_response_factory=lambda **kwargs: kwargs,
    )
    defaults.update(overrides)
    return DocumentPostprocessRuntime(**defaults)


def test_document_postprocess_runtime_coordinates_post_parse_pipeline() -> None:
    quality_runtime = _QualityRuntime()
    artifact_runtime = _ArtifactRuntime()
    diagnostics_runtime = _DiagnosticsRuntime()
    response_runtime = _ResponseRuntime()
    runtime = _build_runtime(
        post_parse_quality_runtime=quality_runtime,
        post_parse_artifact_runtime=artifact_runtime,
        diagnostics_builder_runtime=diagnostics_runtime,
        extraction_response_runtime=response_runtime,
    )

    bundle = runtime.build_response_bundle(
        file_name="demo.docx",
        file_hash="hash123",
        schema_hash="schema123",
        cache_key="cache123",
        parse_input_name="demo.pdf",
        parse_input_bytes=b"%PDF",
        parse_track="VisualTrack",
        parse_ms=120,
        extract_ms=240,
        total_ms=420,
        parse_warning="seed",
        parse_timeout_sec=90.0,
        extract_timeout_sec=180.0,
        nonpdf_total_budget_sec=150.0,
        word_parse_via_pdf=True,
        word_parse_extract_budget_sec=60.0,
        word_convert_budget_sec=30.0,
        dynamic_extract_timeout_meta={"applied": True},
        schema_meta={"mode": "auto"},
        allow_schema_llm=True,
        schema_context_preview="schema preview",
        file_size_mb=0.55,
        naming_template="finance_document",
        used_quick_fallback=False,
        chain_contract={"required": True, "satisfied": True},
        final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
        effective_schema_fields={"amount": {"type": "number"}},
        marked_markdown="markdown",
        bbox_map={"r1": [1.0]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        conversion_diag={"seed": "ok"},
        parse_stats={"chain_status": "success"},
        nonpdf_preflight={"profile": "mixed"},
        nonpdf_budget={"parse_timeout_sec": 24.0},
    )

    assert bundle.response == "response-obj"
    assert bundle.cache_payload == {"cache_key": "cache123"}
    assert quality_runtime.calls[0]["parse_warning"] == "seed"
    assert artifact_runtime.build_calls[0]["final_results"] == {"amount": {"value": 100}}
    assert diagnostics_runtime.calls[0]["graph_diagnostics"] == {"prompt_version": "v1"}
    assert diagnostics_runtime.calls[0]["business_extraction_status"] == "nonempty"
    assert diagnostics_runtime.calls[0]["trace_stats"] == {"trace_hit_count": 1}
    assert diagnostics_runtime.calls[0]["conversion_diag"] == {"pdf_preview_url": "/extract/artifact/preview.pdf"}
    assert diagnostics_runtime.calls[0]["is_word_document"] is True
    assert artifact_runtime.enrich_calls[0]["diagnostics"] == {"seed": True}
    assert response_runtime.calls[0]["diagnostics"] == {"seed": True, "enriched": True}
    assert response_runtime.calls[0]["soft_warnings"] == ["artifact-warning"]
    assert response_runtime.calls[0]["trace_hits"] == [{"object_type": "field"}]


def test_document_postprocess_runtime_filters_non_dict_optional_payloads() -> None:
    diagnostics_runtime = _DiagnosticsRuntime()
    runtime = _build_runtime(
        diagnostics_builder_runtime=diagnostics_runtime,
        is_word_file=lambda file_name: False,
    )

    runtime.build_response_bundle(
        file_name="demo.txt",
        file_hash="hash456",
        schema_hash="schema456",
        cache_key="cache456",
        parse_input_name="demo.txt",
        parse_input_bytes=b"text",
        parse_track="FastTrack",
        parse_ms=10,
        extract_ms=20,
        total_ms=30,
        parse_warning="",
        parse_timeout_sec=15.0,
        extract_timeout_sec=25.0,
        nonpdf_total_budget_sec=None,
        word_parse_via_pdf=False,
        word_parse_extract_budget_sec=None,
        word_convert_budget_sec=None,
        dynamic_extract_timeout_meta={},
        schema_meta={},
        allow_schema_llm=False,
        schema_context_preview="",
        file_size_mb=0.01,
        naming_template="common_document",
        used_quick_fallback=True,
        chain_contract={"required": False, "satisfied": False},
        final_state={"results": {}, "errors": [], "soft_warnings": []},
        effective_schema_fields={},
        marked_markdown="markdown",
        bbox_map={},
        table_blocks=[],
        figure_blocks=[],
        conversion_diag={},
        parse_stats=["bad"],
        nonpdf_preflight=["bad"],
        nonpdf_budget=["bad"],
    )

    assert diagnostics_runtime.calls[0]["parse_stats"] is None
    assert diagnostics_runtime.calls[0]["nonpdf_preflight"] is None
    assert diagnostics_runtime.calls[0]["nonpdf_budget"] is None
    assert diagnostics_runtime.calls[0]["is_word_document"] is False


def test_document_postprocess_runtime_accepts_dependency_bundle() -> None:
    quality_runtime = _QualityRuntime()
    artifact_runtime = _ArtifactRuntime()
    diagnostics_runtime = _DiagnosticsRuntime()
    response_runtime = _ResponseRuntime()
    runtime = DocumentPostprocessRuntime(
        dependency_bundle=DocumentPostprocessDependencyBundle(
            post_parse_quality_runtime=quality_runtime,
            post_parse_artifact_runtime=artifact_runtime,
            diagnostics_builder_runtime=diagnostics_runtime,
            extraction_response_runtime=response_runtime,
            graph_diagnostics_factory=lambda: {"prompt_version": "v2"},
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
            current_extraction_logic_version=lambda: "logic-v2",
            current_extraction_logic_components=lambda: {"fingerprint": "bundle"},
            field_naming_version="naming-v2",
            schema_rule_versions={"selection": "bundle"},
            normalize_soft_warnings=lambda value: value,
            is_low_value_auto_schema_field_name=lambda value: False,
            has_meaningful_value=lambda value: True,
            is_low_value_quick_fallback_value=lambda value: False,
            is_recoverable_timeout_error=lambda value: False,
            filter_low_value_auto_results=lambda results: (results, {}),
            effective_quality_schema_fields=lambda schema_fields, removed: schema_fields,
            result_quality_snapshot=lambda results, schema_fields: {"coverage_ratio": 1.0},
            strip_recovered_extract_warnings=lambda warnings, **kwargs: warnings,
            write_artifact_bytes=lambda **kwargs: ("frag", "/artifact"),
            build_document_trace_hits=lambda **kwargs: [],
            trace_stats_builder=lambda hits: {"trace_hit_count": len(hits)},
            build_polymorphic_links=lambda **kwargs: [],
            count_table_cells=lambda table_blocks: 0,
            table_quality_avg=lambda table_blocks: 0.0,
            table_source_counts=lambda table_blocks: {},
            count_figure_dataframe_cells=lambda figure_blocks: 0,
            figure_pages=lambda figure_blocks: [],
            figure_source_counts=lambda figure_blocks: {},
            persist_assistant1_source_markdown_artifact=lambda **kwargs: ("", "", "", ""),
            persist_assistant_payload_artifact=lambda **kwargs: ("", ""),
            promote_visual_diagnostics=lambda payload: payload,
            extraction_result_factory=lambda payload: payload,
            document_response_factory=lambda **kwargs: kwargs,
        )
    )

    bundle = runtime.build_response_bundle(
        file_name="demo.docx",
        file_hash="hash-bundle",
        schema_hash="schema-bundle",
        cache_key="cache-bundle",
        parse_input_name="demo.pdf",
        parse_input_bytes=b"%PDF",
        parse_track="VisualTrack",
        parse_ms=10,
        extract_ms=20,
        total_ms=30,
        parse_warning="",
        parse_timeout_sec=40.0,
        extract_timeout_sec=50.0,
        nonpdf_total_budget_sec=None,
        word_parse_via_pdf=True,
        word_parse_extract_budget_sec=12.0,
        word_convert_budget_sec=8.0,
        dynamic_extract_timeout_meta={"bundle": True},
        schema_meta={"mode": "auto"},
        allow_schema_llm=True,
        schema_context_preview="preview",
        file_size_mb=0.2,
        naming_template="bundle_document",
        used_quick_fallback=False,
        chain_contract={"required": True, "satisfied": True},
        final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
        effective_schema_fields={"amount": {"type": "number"}},
        marked_markdown="markdown",
        bbox_map={"r1": [1.0]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        conversion_diag={},
        parse_stats={"chain_status": "success"},
        nonpdf_preflight={"profile": "mixed"},
        nonpdf_budget={"parse_timeout_sec": 24.0},
    )

    assert bundle.response == "response-obj"
    assert diagnostics_runtime.calls[0]["graph_diagnostics"] == {"prompt_version": "v2"}
    assert response_runtime.calls[0]["cache_key"] == "cache-bundle"


def test_document_postprocess_runtime_builds_bundle_from_pipeline_outcome() -> None:
    response_runtime = _ResponseRuntime()
    runtime = _build_runtime(extraction_response_runtime=response_runtime)
    pipeline_outcome = SimpleNamespace(
        parse_input_name="demo.pdf",
        parse_input_bytes=b"%PDF",
        parse_track="VisualTrack",
        parse_ms=15,
        extract_ms=25,
        parse_warning="seed",
        parse_timeout_sec=45.0,
        extract_timeout_sec=55.0,
        nonpdf_total_budget_sec=120.0,
        word_parse_via_pdf=True,
        word_parse_extract_budget_sec=20.0,
        word_convert_budget_sec=10.0,
        dynamic_extract_timeout_meta={"boost": True},
        schema_meta={"mode": "auto"},
        allow_schema_llm=True,
        schema_context_preview="preview",
        file_size_mb=0.4,
        naming_template="pipeline_document",
        used_quick_fallback=False,
        chain_contract={"required": True, "satisfied": True},
        final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
        effective_schema_fields={"amount": {"type": "number"}},
        marked_markdown="markdown",
        bbox_map={"r1": [1.0]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        conversion_diag={"seed": "ok"},
        parse_stats={"chain_status": "success"},
        nonpdf_preflight={"profile": "mixed"},
        nonpdf_budget={"parse_timeout_sec": 24.0},
    )

    bundle = runtime.build_pipeline_response_bundle(
        file_name="demo.docx",
        file_hash="hash-pipeline",
        schema_hash="schema-pipeline",
        cache_key="cache-pipeline",
        pipeline_outcome=pipeline_outcome,
        total_ms=40,
    )

    assert bundle.response == "response-obj"
    assert response_runtime.calls[0]["track"] == "VisualTrack"
    assert response_runtime.calls[0]["diagnostics"] == {"seed": True, "enriched": True}
