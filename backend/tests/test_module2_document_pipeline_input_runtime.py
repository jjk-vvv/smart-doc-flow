from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace


document_pipeline_input_runtime_module = importlib.import_module("module2.app.core.pipeline.document_pipeline_stages_runtime")
DocumentPipelineInputRuntime = document_pipeline_input_runtime_module.DocumentPipelineInputRuntime


class _DocumentInputPlanRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_plan(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_timeout_sec=120.0,
            extract_timeout_sec=180.0,
            nonpdf_preflight={"profile": "mixed"},
            nonpdf_budget={"parse_timeout_sec": 60.0},
            nonpdf_total_budget_sec=240.0,
            nonpdf_guard_sec=2.0,
            word_parse_extract_budget_sec=70.0,
            word_convert_budget_sec=35.0,
            word_parse_via_pdf=True,
            input_is_word=True,
        )


class _WordInputPreparationRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def prepare(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            parse_track="VisualTrack",
            parse_warning="word-warning",
            conversion_diag={"office_pdf_converted": True},
            word_suffix=".docx",
        )


async def _emit_progress(*args, **kwargs):
    return None


def test_document_pipeline_input_runtime_prepares_input_plan_and_word_input() -> None:
    runtime = DocumentPipelineInputRuntime()
    document_input_plan_runtime = _DocumentInputPlanRuntime()
    word_input_preparation_runtime = _WordInputPreparationRuntime()

    outcome = asyncio.run(
        runtime.prepare(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            initial_track="FastTrack",
            started_at_sec=50.0,
            document_input_plan_runtime=document_input_plan_runtime,
            preflight_nonpdf_profile=lambda **kwargs: {"profile": "mixed"},
            resolve_nonpdf_budgets=lambda profile: {"parse_timeout_sec": 60.0},
            resolve_nonpdf_plan=lambda **kwargs: SimpleNamespace(
                parse_timeout_sec=60.0,
                extract_timeout_sec=90.0,
                nonpdf_total_budget_sec=180.0,
                word_parse_extract_budget_sec=70.0,
                word_convert_budget_sec=35.0,
            ),
            apply_field_extract_timeout_floor=lambda extract_timeout_sec: extract_timeout_sec,
            word_pdf_required=lambda: True,
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
            word_input_preparation_runtime=word_input_preparation_runtime,
            office_convert_enabled=lambda: True,
            docx_native_recovery_enabled=lambda: True,
            validate_word_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
            resolve_conversion_timeout=lambda **kwargs: SimpleNamespace(timeout_sec=30.0, exhausted_detail=""),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: SimpleNamespace(),
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=SimpleNamespace(),
            ensure_preview_job_started=lambda **kwargs: None,
            await_or_reuse_pdf=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            convert_doc_to_docx_with_timeout=lambda **kwargs: (b"", {}),
        )
    )

    assert document_input_plan_runtime.calls[0]["file_name"] == "demo.docx"
    assert word_input_preparation_runtime.calls[0]["parse_track"] == "FastTrack"
    assert word_input_preparation_runtime.calls[0]["word_parse_via_pdf"] is True
    assert outcome.parse_timeout_sec == 120.0
    assert outcome.extract_timeout_sec == 180.0
    assert outcome.nonpdf_preflight == {"profile": "mixed"}
    assert outcome.parse_input_name == "demo.pdf"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "word-warning"
    assert outcome.conversion_diag == {"office_pdf_converted": True}
    assert outcome.word_suffix == ".docx"
