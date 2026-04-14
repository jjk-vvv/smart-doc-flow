from __future__ import annotations

import asyncio
import importlib
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import HTTPException


word_conversion_execution_runtime_module = importlib.import_module("app.modules.module2.core.format.word_input_preparation_runtime")
WordConversionExecutionRuntime = word_conversion_execution_runtime_module.WordConversionExecutionRuntime


class _ConversionDecision:
    def __init__(self, timeout_sec, exhausted_detail: str = "") -> None:
        self.timeout_sec = timeout_sec
        self.exhausted_detail = exhausted_detail


def test_word_conversion_execution_runtime_converts_docx_via_pdf_successfully() -> None:
    runtime = WordConversionExecutionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_PDF_TIMEOUT_SEC": "60",
        }.get(key, default),
        perf_counter=lambda: 50.0,
    )
    events: list[tuple[str, object]] = []

    @asynccontextmanager
    async def _semaphore():
        events.append(("enter", "word_pdf"))
        try:
            yield
        finally:
            events.append(("exit", "word_pdf"))

    async def _emit_progress(stage, ratio, message="", extra=None):
        events.append((stage, ratio))

    async def _ensure_preview_job_started(**kwargs):
        events.append(("ensure_preview_job_started", dict(kwargs)))
        return SimpleNamespace(error="", job_id="job-123")

    async def _await_or_reuse_pdf(**kwargs):
        events.append(("await_or_reuse_pdf", dict(kwargs)))
        return (b"%PDF-converted", {"artifact_path": "preview/demo.pdf", "artifact_url": "/artifact/demo.pdf"})

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        events.append(("heartbeat", dict(kwargs)))
        return await awaitable

    async def _run():
        return await runtime.prepare_word_via_pdf(
            file_name="report.docx",
            file_bytes=b"docx",
            file_hash="hash456",
            parse_timeout_sec=42.0,
            extract_timeout_sec=72.0,
            nonpdf_total_budget_sec=150.0,
            word_convert_budget_sec=30.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            word_suffix=".docx",
            word_parse_via_pdf=True,
            docx_native_recovery_enabled=True,
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(24.0),
            build_word_pdf_success=lambda **kwargs: {
                "parse_input_name": "report.pdf",
                "parse_track": "VisualTrack",
                "conversion_diag": {"office_pdf_converted": True},
            },
            resolve_word_pdf_failure=lambda **kwargs: None,
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=_ensure_preview_job_started,
            await_or_reuse_pdf=_await_or_reuse_pdf,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "report.pdf"
    assert outcome.parse_input_bytes == b"%PDF-converted"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == ""
    assert outcome.conversion_diag == {"office_pdf_converted": True}
    assert ("converting", 0.14) in events
    assert ("converting", 0.24) in events
    assert any(item[0] == "ensure_preview_job_started" for item in events)


def test_word_conversion_execution_runtime_falls_back_to_native_docx_after_pdf_failure() -> None:
    runtime = WordConversionExecutionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_PDF_TIMEOUT_SEC": "60",
            "MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK": "true",
        }.get(key, default),
        perf_counter=lambda: 25.0,
    )
    progress_events: list[tuple[str, float, str]] = []

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(stage, ratio, message="", extra=None):
        progress_events.append((stage, ratio, message))

    async def _ensure_preview_job_started(**kwargs):
        return SimpleNamespace(error="preview failed")

    async def _await_or_reuse_pdf(**kwargs):
        return (None, {"office_pdf_preview_error": "preview failed"})

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _run():
        return await runtime.prepare_word_via_pdf(
            file_name="report.docx",
            file_bytes=b"docx",
            file_hash="hash789",
            parse_timeout_sec=42.0,
            extract_timeout_sec=72.0,
            nonpdf_total_budget_sec=150.0,
            word_convert_budget_sec=30.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=5.0,
            word_suffix=".docx",
            word_parse_via_pdf=True,
            docx_native_recovery_enabled=True,
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(20.0),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: SimpleNamespace(
                conversion_diag={"office_pdf_converted": False},
                emit_progress_message="switch native docx",
                should_raise=False,
                terminal_status_code=None,
                terminal_detail="",
                parse_track="NativeDocx",
                parse_warning="docx_native_recovery_after_pdf_failure",
                use_original_input=True,
            ),
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=_ensure_preview_job_started,
            await_or_reuse_pdf=_await_or_reuse_pdf,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "report.docx"
    assert outcome.parse_input_bytes == b"docx"
    assert outcome.parse_track == "NativeDocx"
    assert outcome.parse_warning == "docx_native_recovery_after_pdf_failure"
    assert outcome.conversion_diag == {"office_pdf_converted": False}
    assert ("converting", 0.24, "switch native docx") in progress_events


def test_word_conversion_execution_runtime_converts_doc_to_docx_for_fasttrack() -> None:
    runtime = WordConversionExecutionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_DOCX_TIMEOUT_SEC": "45",
        }.get(key, default),
        perf_counter=lambda: 100.0,
    )

    async def _convert_doc_to_docx_with_timeout(**kwargs):
        return (b"docx-bytes", {"converter": "soffice", "elapsed_ms": 222})

    async def _run():
        return await runtime.prepare_doc_to_docx_fasttrack(
            file_name="legacy.doc",
            file_bytes=b"doc",
            parse_timeout_sec=24.0,
            extract_timeout_sec=48.0,
            nonpdf_total_budget_sec=90.0,
            word_convert_budget_sec=22.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(18.0),
            build_doc_to_docx_success=lambda **kwargs: {
                "parse_input_name": "legacy.docx",
                "conversion_diag": {"doc_to_docx_converted": True},
            },
            build_doc_to_docx_failure=lambda **kwargs: {},
            convert_doc_to_docx_with_timeout=_convert_doc_to_docx_with_timeout,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "legacy.docx"
    assert outcome.parse_input_bytes == b"docx-bytes"
    assert outcome.parse_track == "FastTrack"
    assert outcome.parse_warning == ""
    assert outcome.conversion_diag == {"doc_to_docx_converted": True}


def test_word_conversion_execution_runtime_raises_when_doc_budget_exhausted() -> None:
    runtime = WordConversionExecutionRuntime(perf_counter=lambda: 15.0)

    async def _run():
        return await runtime.prepare_doc_to_docx_fasttrack(
            file_name="legacy.doc",
            file_bytes=b"doc",
            parse_timeout_sec=24.0,
            extract_timeout_sec=48.0,
            nonpdf_total_budget_sec=90.0,
            word_convert_budget_sec=22.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(None, "budget exhausted"),
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    try:
        asyncio.run(_run())
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 504
        assert exc.detail == "budget exhausted"


def test_word_conversion_execution_runtime_raises_when_doc_conversion_fails() -> None:
    runtime = WordConversionExecutionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_DOCX_TIMEOUT_SEC": "45",
        }.get(key, default),
        perf_counter=lambda: 100.0,
    )

    async def _convert_doc_to_docx_with_timeout(**kwargs):
        raise RuntimeError("conversion failed")

    async def _run():
        return await runtime.prepare_doc_to_docx_fasttrack(
            file_name="legacy.doc",
            file_bytes=b"doc",
            parse_timeout_sec=24.0,
            extract_timeout_sec=48.0,
            nonpdf_total_budget_sec=90.0,
            word_convert_budget_sec=22.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(18.0),
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {
                "terminal_status_code": 422,
                "terminal_detail": "doc conversion failed",
            },
            convert_doc_to_docx_with_timeout=_convert_doc_to_docx_with_timeout,
        )

    try:
        asyncio.run(_run())
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "doc conversion failed"
