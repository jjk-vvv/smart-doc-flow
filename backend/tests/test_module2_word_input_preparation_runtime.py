from __future__ import annotations

import asyncio
import importlib
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import HTTPException


word_input_preparation_runtime_module = importlib.import_module("module2.app.core.format.word_input_preparation_runtime")
WordInputPreparationRuntime = word_input_preparation_runtime_module.WordInputPreparationRuntime


class _ConversionDecision:
    def __init__(self, timeout_sec, exhausted_detail: str = "") -> None:
        self.timeout_sec = timeout_sec
        self.exhausted_detail = exhausted_detail


def test_word_input_preparation_runtime_keeps_non_word_inputs_unchanged() -> None:
    runtime = WordInputPreparationRuntime(perf_counter=lambda: 10.0)

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(*args, **kwargs):
        raise AssertionError("non-word input should not emit conversion progress")

    async def _run():
        return await runtime.prepare(
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            file_hash="hash123",
            parse_track="VisualTrack",
            parse_warning="seed",
            parse_timeout_sec=60.0,
            extract_timeout_sec=90.0,
            nonpdf_total_budget_sec=None,
            word_convert_budget_sec=None,
            nonpdf_guard_sec=2.0,
            started_at_sec=1.0,
            input_is_word=False,
            word_parse_via_pdf=True,
            office_convert_enabled=True,
            docx_native_recovery_enabled=False,
            validate_preconditions=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not validate")),
            resolve_conversion_timeout=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not resolve")),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: None,
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=lambda **kwargs: None,
            await_or_reuse_pdf=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "demo.pdf"
    assert outcome.parse_input_bytes == b"%PDF"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "seed"
    assert outcome.conversion_diag == {}
    assert outcome.word_suffix == ".pdf"


def test_word_input_preparation_runtime_converts_docx_via_pdf_successfully() -> None:
    runtime = WordInputPreparationRuntime(
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
        return await runtime.prepare(
            file_name="report.docx",
            file_bytes=b"docx",
            file_hash="hash456",
            parse_track="FastTrack",
            parse_warning="",
            parse_timeout_sec=42.0,
            extract_timeout_sec=72.0,
            nonpdf_total_budget_sec=150.0,
            word_convert_budget_sec=30.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            input_is_word=True,
            word_parse_via_pdf=True,
            office_convert_enabled=True,
            docx_native_recovery_enabled=True,
            validate_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(24.0),
            build_word_pdf_success=lambda **kwargs: {
                "parse_input_name": "report.pdf",
                "parse_track": "VisualTrack",
                "conversion_diag": {"office_pdf_converted": True},
            },
            resolve_word_pdf_failure=lambda **kwargs: None,
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=_ensure_preview_job_started,
            await_or_reuse_pdf=_await_or_reuse_pdf,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "report.pdf"
    assert outcome.parse_input_bytes == b"%PDF-converted"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == ""
    assert outcome.conversion_diag == {"office_pdf_converted": True}
    assert outcome.word_suffix == ".docx"
    assert ("converting", 0.14) in events
    assert ("converting", 0.24) in events
    assert events[0] == ("converting", 0.14)
    assert any(item[0] == "ensure_preview_job_started" for item in events)


def test_word_input_preparation_runtime_resolves_word_pdf_failure_to_native_docx_recovery() -> None:
    runtime = WordInputPreparationRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_PDF_TIMEOUT_SEC": "60",
            "MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK": "true",
        }.get(key, default),
        perf_counter=lambda: 25.0,
    )

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(*args, **kwargs):
        return None

    async def _ensure_preview_job_started(**kwargs):
        return SimpleNamespace(error="preview failed")

    async def _await_or_reuse_pdf(**kwargs):
        return (None, {"office_pdf_preview_error": "preview failed"})

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _run():
        return await runtime.prepare(
            file_name="report.docx",
            file_bytes=b"docx",
            file_hash="hash789",
            parse_track="VisualTrack",
            parse_warning="",
            parse_timeout_sec=42.0,
            extract_timeout_sec=72.0,
            nonpdf_total_budget_sec=150.0,
            word_convert_budget_sec=30.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=5.0,
            input_is_word=True,
            word_parse_via_pdf=True,
            office_convert_enabled=True,
            docx_native_recovery_enabled=True,
            validate_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
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
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=_ensure_preview_job_started,
            await_or_reuse_pdf=_await_or_reuse_pdf,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "report.docx"
    assert outcome.parse_input_bytes == b"docx"
    assert outcome.parse_track == "NativeDocx"
    assert outcome.parse_warning == "docx_native_recovery_after_pdf_failure"
    assert outcome.conversion_diag == {"office_pdf_converted": False}


def test_word_input_preparation_runtime_converts_doc_to_docx_for_fasttrack() -> None:
    runtime = WordInputPreparationRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_DOC_TO_DOCX_TIMEOUT_SEC": "45",
        }.get(key, default),
        perf_counter=lambda: 100.0,
    )

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(*args, **kwargs):
        return None

    async def _convert_doc_to_docx_with_timeout(**kwargs):
        return (b"docx-bytes", {"converter": "soffice", "elapsed_ms": 222})

    async def _run():
        return await runtime.prepare(
            file_name="legacy.doc",
            file_bytes=b"doc",
            file_hash="hash000",
            parse_track="VisualTrack",
            parse_warning="",
            parse_timeout_sec=24.0,
            extract_timeout_sec=48.0,
            nonpdf_total_budget_sec=90.0,
            word_convert_budget_sec=22.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            input_is_word=True,
            word_parse_via_pdf=False,
            office_convert_enabled=True,
            docx_native_recovery_enabled=False,
            validate_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(18.0),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: None,
            build_doc_to_docx_success=lambda **kwargs: {
                "parse_input_name": "legacy.docx",
                "conversion_diag": {"doc_to_docx_converted": True},
            },
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=lambda **kwargs: None,
            await_or_reuse_pdf=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            convert_doc_to_docx_with_timeout=_convert_doc_to_docx_with_timeout,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "legacy.docx"
    assert outcome.parse_input_bytes == b"docx-bytes"
    assert outcome.parse_track == "FastTrack"
    assert outcome.parse_warning == ""
    assert outcome.conversion_diag == {"doc_to_docx_converted": True}
    assert outcome.word_suffix == ".doc"


def test_word_input_preparation_runtime_raises_when_budget_exhausted_before_doc_conversion() -> None:
    runtime = WordInputPreparationRuntime(perf_counter=lambda: 15.0)

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.prepare(
            file_name="legacy.doc",
            file_bytes=b"doc",
            file_hash="hash999",
            parse_track="FastTrack",
            parse_warning="",
            parse_timeout_sec=24.0,
            extract_timeout_sec=48.0,
            nonpdf_total_budget_sec=90.0,
            word_convert_budget_sec=22.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=10.0,
            input_is_word=True,
            word_parse_via_pdf=False,
            office_convert_enabled=True,
            docx_native_recovery_enabled=False,
            validate_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
            resolve_conversion_timeout=lambda **kwargs: _ConversionDecision(None, "budget exhausted"),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: None,
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=lambda **kwargs: None,
            await_or_reuse_pdf=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    try:
        asyncio.run(_run())
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 504
        assert exc.detail == "budget exhausted"


def test_word_input_preparation_runtime_delegates_word_pdf_branch_to_execution_runtime() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _StubConversionRuntime:
        async def prepare_word_via_pdf(self, **kwargs):
            calls.append(("prepare_word_via_pdf", dict(kwargs)))
            return SimpleNamespace(
                parse_input_name="delegated.pdf",
                parse_input_bytes=b"%PDF",
                parse_track="VisualTrack",
                parse_warning="",
                conversion_diag={"delegated": True},
            )

        async def prepare_doc_to_docx_fasttrack(self, **kwargs):
            raise AssertionError("doc fasttrack should not be called in pdf branch")

    runtime = WordInputPreparationRuntime(
        perf_counter=lambda: 10.0,
        word_conversion_execution_runtime=_StubConversionRuntime(),
    )

    @asynccontextmanager
    async def _semaphore():
        yield

    async def _emit_progress(*args, **kwargs):
        raise AssertionError("delegated branch should own progress emission")

    async def _run():
        return await runtime.prepare(
            file_name="report.docx",
            file_bytes=b"docx",
            file_hash="hash-delegated",
            parse_track="FastTrack",
            parse_warning="",
            parse_timeout_sec=42.0,
            extract_timeout_sec=72.0,
            nonpdf_total_budget_sec=150.0,
            word_convert_budget_sec=30.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=1.0,
            input_is_word=True,
            word_parse_via_pdf=True,
            office_convert_enabled=True,
            docx_native_recovery_enabled=True,
            validate_preconditions=lambda **kwargs: SimpleNamespace(should_raise=False),
            resolve_conversion_timeout=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should delegate")),
            build_word_pdf_success=lambda **kwargs: {},
            resolve_word_pdf_failure=lambda **kwargs: None,
            build_doc_to_docx_success=lambda **kwargs: {},
            build_doc_to_docx_failure=lambda **kwargs: {},
            emit_progress=_emit_progress,
            word_pdf_semaphore=_semaphore(),
            ensure_preview_job_started=lambda **kwargs: None,
            await_or_reuse_pdf=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            convert_doc_to_docx_with_timeout=lambda **kwargs: None,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_input_name == "delegated.pdf"
    assert outcome.parse_input_bytes == b"%PDF"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == ""
    assert outcome.conversion_diag == {"delegated": True}
    assert outcome.word_suffix == ".docx"
    assert len(calls) == 1
    assert calls[0][0] == "prepare_word_via_pdf"
