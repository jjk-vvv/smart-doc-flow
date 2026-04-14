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


diagnostics_builder_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_postprocess_runtime.py"],
    "_smart_doc_flow_module2_diagnostics_builder_runtime",
)

DiagnosticsBuilderRuntime = diagnostics_builder_runtime_module.DiagnosticsBuilderRuntime


def test_diagnostics_builder_runtime_builds_contracts_and_parse_stats_projection() -> None:
    runtime = DiagnosticsBuilderRuntime()

    outcome = runtime.build(
        parse_ms=120,
        extract_ms=240,
        total_ms=420,
        parse_input_name="demo.pdf",
        parse_input_bytes=b"payload",
        markdown="markdown body",
        bbox_map={"r1": [1, 2, 3, 4]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        soft_warnings=["quality_gate_ok"],
        parse_timeout_sec=90.0,
        extract_timeout_sec=180.0,
        nonpdf_total_budget_sec=None,
        word_parse_via_pdf=True,
        word_parse_extract_budget_sec=60.0,
        word_convert_budget_sec=30.0,
        dynamic_extract_timeout_meta={"applied": True},
        schema_meta={
            "mode": "auto",
            "source": "rules+heuristic",
            "field_count": 2,
            "fields": ["project_name", "invoice_total"],
            "raw_fields": ["项目名称", "总金额"],
            "field_name_mappings": {"项目名称": "project_name"},
            "naming_template": "finance_document",
            "naming_stats": {"normalized": 2},
            "llm_attempted": False,
            "llm_used": False,
            "rule_field_count": 1,
            "heuristic_field_count": 1,
            "deterministic_field_count": 2,
        },
        allow_schema_llm=True,
        schema_context_preview="schema preview text",
        file_size_mb=0.55,
        naming_template="finance_document",
        graph_diagnostics={
            "prompt_version": "prompt-v1",
            "prompt_names": ["extract_fields"],
            "prompt_versions": {"extract_fields": "v3"},
        },
        used_quick_fallback=False,
        quality_schema_fields={"project_name": {}, "invoice_total": {}},
        semantic_removed={"discarded": "low_value"},
        degraded_reasons=["low_coverage:0.25"],
        quality_snapshot={"filled_fields": 1, "target_fields": 2, "coverage_ratio": 0.5, "avg_confidence": 0.82},
        polymorphic_links=[{"field": "project_name", "ref_id": "r1"}],
        business_extraction_status="nonempty",
        chain_contract={
            "required": True,
            "satisfied": True,
            "artifact_status": "ready",
            "vision_status": "ok",
            "mineru_status": "ok",
            "parse_track": "VisualTrack",
            "pipeline": "visual_pdf",
            "reasons": ["mineru_ok"],
        },
        conversion_diag={"pdf_preview_url": "/artifacts/preview/demo.pdf"},
        trace_stats={"trace_hit_count": 3},
        parse_stats={
            "chain_status": "success",
            "visual_pdf_profile": "dense",
            "visual_mode": "layout+vision",
            "visual_text_only_recovery": "disabled",
            "docx_chart_xml_seen": 2,
            "mineru_run": {
                "status": "ok",
                "text_only_short_circuit": True,
                "text_only_short_circuit_method": "vision_skip",
            },
        },
        nonpdf_preflight={"profile": "mixed", "signals": {"tables": 2}},
        nonpdf_budget={"parse_budget_sec": 30.0},
        current_extraction_logic_version=lambda: "logic-v1",
        current_extraction_logic_components=lambda: {"fingerprint": "abc123"},
        count_table_cells=lambda table_blocks: 12,
        table_quality_avg=lambda table_blocks: 0.91,
        table_source_counts=lambda table_blocks: {"pdf_native": 1},
        count_figure_dataframe_cells=lambda figure_blocks: 8,
        figure_pages=lambda figure_blocks: [1],
        figure_source_counts=lambda figure_blocks: {"vision": 1},
        field_naming_version="naming-v1",
        schema_rule_versions={"selection": "20260323"},
        is_word_document=True,
    )

    assert outcome.parse_contract["status"] == "success"
    assert outcome.parse_contract["visual_mode"] == "layout+vision"
    assert outcome.parse_contract["text_only_short_circuit"] is True
    assert outcome.business_extraction_contract["quality_status"] == "degraded"
    assert outcome.diagnostics["parse_input_bytes"] == len(b"payload")
    assert outcome.diagnostics["schema_llm_planner_enabled"] is True
    assert outcome.diagnostics["schema_llm_planner_attempted"] is False
    assert outcome.diagnostics["schema_llm_planner_used"] is False
    assert outcome.diagnostics["schema_rule_field_count"] == 1
    assert outcome.diagnostics["field_naming_template"] == "finance_document"
    assert outcome.diagnostics["mineru_status"] == "ok"
    assert outcome.diagnostics["parse_stats"]["business_extraction_status"] == "nonempty"
    assert outcome.diagnostics["docx_chart_xml_seen"] == 2
    assert outcome.diagnostics["trace_hit_count"] == 3
    assert outcome.diagnostics["pdf_preview_url"] == "/artifacts/preview/demo.pdf"
    assert outcome.diagnostics["nonpdf_budget"]["parse_budget_sec"] == 30.0
    assert outcome.diagnostics["word_pdf_required"] is True


def test_diagnostics_builder_runtime_handles_non_word_without_optional_payloads() -> None:
    runtime = DiagnosticsBuilderRuntime()

    outcome = runtime.build(
        parse_ms=10,
        extract_ms=20,
        total_ms=30,
        parse_input_name="demo.txt",
        parse_input_bytes=b"abc",
        markdown="hello",
        bbox_map={},
        table_blocks=[],
        figure_blocks=[],
        soft_warnings=[],
        parse_timeout_sec=15.0,
        extract_timeout_sec=25.0,
        nonpdf_total_budget_sec=40.0,
        word_parse_via_pdf=False,
        word_parse_extract_budget_sec=None,
        word_convert_budget_sec=None,
        dynamic_extract_timeout_meta={},
        schema_meta={},
        allow_schema_llm=False,
        schema_context_preview="",
        file_size_mb=0.01,
        naming_template="common_document",
        graph_diagnostics={},
        used_quick_fallback=True,
        quality_schema_fields={},
        semantic_removed={},
        degraded_reasons=[],
        quality_snapshot={},
        polymorphic_links=[],
        business_extraction_status="empty_valid",
        chain_contract={"required": False, "satisfied": False, "reasons": []},
        conversion_diag={},
        trace_stats={},
        parse_stats=None,
        nonpdf_preflight=None,
        nonpdf_budget=None,
        current_extraction_logic_version=lambda: "logic-v2",
        current_extraction_logic_components=lambda: {"fingerprint": "xyz789"},
        count_table_cells=lambda table_blocks: 0,
        table_quality_avg=lambda table_blocks: 0.0,
        table_source_counts=lambda table_blocks: {},
        count_figure_dataframe_cells=lambda figure_blocks: 0,
        figure_pages=lambda figure_blocks: [],
        figure_source_counts=lambda figure_blocks: {},
        field_naming_version="naming-v2",
        schema_rule_versions={},
        is_word_document=False,
    )

    assert outcome.parse_contract["status"] == "failed"
    assert outcome.business_extraction_contract["status"] == "empty_valid"
    assert outcome.diagnostics["word_pdf_required"] is False
    assert outcome.diagnostics["schema_mode"] == "manual"
    assert outcome.diagnostics["schema_llm_planner_enabled"] is False
    assert outcome.diagnostics["quick_fallback_used"] is True
    assert outcome.diagnostics["soft_warning_count"] == 0
