from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


document_pipeline_finalize_runtime_module = importlib.import_module("app.modules.module2.core.pipeline.document_pipeline_stages_runtime")
DocumentPipelineFinalizeRuntime = document_pipeline_finalize_runtime_module.DocumentPipelineFinalizeRuntime
DocumentPipelineOutcome = document_pipeline_finalize_runtime_module.DocumentPipelineOutcome


def test_document_pipeline_finalize_runtime_resolves_chain_contract_when_satisfied() -> None:
    runtime = DocumentPipelineFinalizeRuntime()

    chain_contract = runtime.resolve_chain_contract(
        file_name="demo.docx",
        parse_input_name="demo.pdf",
        parse_track="VisualTrack",
        word_parse_via_pdf=True,
        conversion_diag={"office_pdf_converted": True},
        parse_stats={"pipeline": "visual_first"},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        build_visual_chain_contract=lambda **kwargs: {
            "required": True,
            "satisfied": True,
            "reasons": [],
            "details": dict(kwargs),
        },
    )

    assert chain_contract["required"] is True
    assert chain_contract["satisfied"] is True
    assert chain_contract["details"]["parse_input_name"] == "demo.pdf"


def test_document_pipeline_finalize_runtime_raises_when_chain_contract_fails() -> None:
    runtime = DocumentPipelineFinalizeRuntime()

    with pytest.raises(HTTPException) as exc_info:
        runtime.resolve_chain_contract(
            file_name="demo.docx",
            parse_input_name="demo.pdf",
            parse_track="VisualTrack",
            word_parse_via_pdf=True,
            conversion_diag={"office_pdf_converted": True},
            parse_stats={"pipeline": "visual_first"},
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            build_visual_chain_contract=lambda **kwargs: {
                "required": True,
                "satisfied": False,
                "reasons": ["missing_visual_chain", "missing_figures"],
            },
        )

    assert exc_info.value.status_code == 503
    assert "missing_visual_chain" in str(exc_info.value.detail)


def test_document_pipeline_finalize_runtime_builds_pipeline_outcome() -> None:
    runtime = DocumentPipelineFinalizeRuntime()

    outcome = runtime.build_outcome(
        parse_timeout_sec=120.0,
        extract_timeout_sec=180.0,
        nonpdf_preflight={"profile": "mixed"},
        nonpdf_budget={"parse_timeout_sec": 60.0},
        nonpdf_total_budget_sec=240.0,
        word_parse_extract_budget_sec=70.0,
        word_convert_budget_sec=35.0,
        word_parse_via_pdf=True,
        parse_input_name="demo.pdf",
        parse_input_bytes=b"%PDF",
        parse_track="VisualTrack",
        parse_warning=None,
        conversion_diag={"office_pdf_converted": True},
        parse_ms=1250,
        chain_contract={"required": True, "satisfied": True, "reasons": []},
        marked_markdown="markdown",
        bbox_map={"r1": [1.0]},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        parse_stats={"pipeline": "visual_first"},
        naming_template="finance_document",
        schema_context_preview="schema preview",
        allow_schema_llm=True,
        effective_schema={"fields": {"amount": {"type": "number"}}},
        schema_meta={"source": "auto", "naming_template": "finance_document"},
        effective_schema_fields={"amount": {"type": "number"}},
        dynamic_extract_timeout_meta={"boost": True},
        file_size_mb=0.42,
        final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
        extract_ms=234,
        used_quick_fallback=False,
    )

    assert isinstance(outcome, DocumentPipelineOutcome)
    assert outcome.parse_input_name == "demo.pdf"
    assert outcome.parse_warning == ""
    assert outcome.chain_contract["satisfied"] is True
    assert outcome.final_state["results"] == {"amount": {"value": 100}}
