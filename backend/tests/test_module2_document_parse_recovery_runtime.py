from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


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


document_parse_recovery_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_parse_recovery_runtime.py"],
    "_smart_doc_flow_module2_document_parse_recovery_runtime",
)

DocumentParseRecoveryRuntime = document_parse_recovery_runtime_module.DocumentParseRecoveryRuntime


@dataclass
class _FallbackOutcome:
    result: object | None = None
    parse_track: str = ""
    parse_warning: str = ""

    @property
    def resolved(self) -> bool:
        return self.result is not None


class _PolicyRuntime:
    def __init__(self, *, timeout_decision=None, exception_decision=None) -> None:
        self.timeout_decision = timeout_decision
        self.exception_decision = exception_decision
        self.timeout_calls: list[dict[str, object]] = []
        self.exception_calls: list[dict[str, object]] = []

    def resolve_timeout_fallback(self, **kwargs):
        self.timeout_calls.append(dict(kwargs))
        return self.timeout_decision

    def resolve_exception_fallback(self, **kwargs):
        self.exception_calls.append(dict(kwargs))
        return self.exception_decision

    @staticmethod
    def append_warning(current_warning, warning: str) -> str:
        current = str(current_warning or "").strip()
        fragment = str(warning or "").strip()
        return fragment if not current else f"{current}|{fragment}"


class _FallbackCoordinator:
    def __init__(self, *, docx_outcome=None, fasttrack_outcome=None) -> None:
        self.docx_outcome = docx_outcome or _FallbackOutcome()
        self.fasttrack_outcome = fasttrack_outcome or _FallbackOutcome()
        self.docx_calls: list[dict[str, object]] = []
        self.fasttrack_calls: list[dict[str, object]] = []

    async def try_docx_native_recovery(self, **kwargs):
        self.docx_calls.append(dict(kwargs))
        return self.docx_outcome

    async def run_fasttrack_fallback(self, **kwargs):
        self.fasttrack_calls.append(dict(kwargs))
        return self.fasttrack_outcome


def test_document_parse_recovery_runtime_returns_primary_parse_result() -> None:
    runtime = DocumentParseRecoveryRuntime(perf_counter=lambda: 10.0)
    captured: dict[str, object] = {}

    async def _parse_attempt_runner(**kwargs):
        captured["runner"] = dict(kwargs)
        return ("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            file_bytes=b"pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"pdf",
            parse_track="VisualTrack",
            parse_timeout_sec=60.0,
            parse_source_file_name=None,
            parse_source_file_bytes=None,
            progress_message="parsing",
            progress_extra={"parse_track": "VisualTrack"},
            resolve_parse_progress_ramp_sec=lambda **kwargs: 24.0,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=_unpack_parse_output,
            visual_parse_policy_runtime=_PolicyRuntime(),
            parse_fallback_coordinator_runtime=_FallbackCoordinator(),
            docx_native_recovery_runtime=object(),
            fasttrack_fallback_runtime=object(),
            word_suffix=".pdf",
            original_file_is_word=False,
            visual_chain_required=True,
            docx_native_recovery_enabled=False,
            visual_strict=False,
            disable_fasttrack_fallback=False,
            nonpdf_total_budget_sec=None,
            started_at_sec=1.0,
            nonpdf_guard_sec=2.0,
            current_parse_warning="seed",
        )

    outcome = asyncio.run(_run())
    assert outcome.marked_markdown == "md"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "seed"
    assert outcome.parse_stats == {"ok": True}
    assert captured["runner"]["context_label"] == "demo.pdf:VisualTrack"
    assert captured["runner"]["heartbeat_message"] == "parsing"


def test_document_parse_recovery_runtime_handles_timeout_with_docx_recovery() -> None:
    runtime = DocumentParseRecoveryRuntime(perf_counter=lambda: 20.0)
    policy_runtime = _PolicyRuntime(
        timeout_decision=SimpleNamespace(
            terminal_status_code=None,
            terminal_detail="",
            docx_native_recovery_reason="word_pdf_parse_timeout",
            try_docx_native_recovery=True,
            should_attempt_fasttrack_fallback=False,
            fallback_timeout_sec=None,
            fallback_context_label="",
            fallback_track="",
            fallback_hint="",
            native_timeout_detail="timeout detail",
        )
    )
    fallback_runtime = _FallbackCoordinator(
        docx_outcome=_FallbackOutcome(
            result=("md", {"r2": [2.0]}, [{"table_id": "t2"}], [], {"recovered": True}),
            parse_track="VisualTrack->NativeDocxRecoveryTimeout",
            parse_warning="recovered",
        )
    )

    async def _parse_attempt_runner(**kwargs):
        raise TimeoutError("slow")

    async def _run():
        return await runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"pdf",
            parse_track="VisualTrack",
            parse_timeout_sec=90.0,
            parse_source_file_name="demo.docx",
            parse_source_file_bytes=b"docx",
            progress_message="parsing",
            progress_extra={},
            resolve_parse_progress_ramp_sec=lambda **kwargs: 30.0,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=lambda parsed: parsed,
            visual_parse_policy_runtime=policy_runtime,
            parse_fallback_coordinator_runtime=fallback_runtime,
            docx_native_recovery_runtime=object(),
            fasttrack_fallback_runtime=object(),
            word_suffix=".docx",
            original_file_is_word=True,
            visual_chain_required=True,
            docx_native_recovery_enabled=True,
            visual_strict=False,
            disable_fasttrack_fallback=False,
            nonpdf_total_budget_sec=120.0,
            started_at_sec=5.0,
            nonpdf_guard_sec=2.0,
            current_parse_warning="seed",
        )

    outcome = asyncio.run(_run())
    assert outcome.marked_markdown == "md"
    assert outcome.parse_track == "VisualTrack->NativeDocxRecoveryTimeout"
    assert outcome.parse_warning == "recovered"
    assert policy_runtime.timeout_calls[0]["original_file_is_word"] is True
    assert fallback_runtime.docx_calls[0]["reason"] == "word_pdf_parse_timeout"


def test_document_parse_recovery_runtime_handles_exception_with_fasttrack_fallback() -> None:
    runtime = DocumentParseRecoveryRuntime(perf_counter=lambda: 30.0)
    policy_runtime = _PolicyRuntime(
        exception_decision=SimpleNamespace(
            docx_native_recovery_reason="word_pdf_visual_error",
            try_docx_native_recovery=False,
            should_attempt_fasttrack_fallback=True,
            fallback_context_label="demo:FastTrackFallback",
            fallback_track="VisualTrack->FastTrackFallback",
            fallback_warning="pdf_visual_timeout_fallback_fasttrack",
            terminal_status_code=None,
            terminal_detail="",
        )
    )
    fallback_runtime = _FallbackCoordinator(
        docx_outcome=_FallbackOutcome(),
        fasttrack_outcome=_FallbackOutcome(
            result=("md-fast", {"r3": [3.0]}, [], [{"figure_id": "f1"}], {"fallback": True}),
            parse_track="VisualTrack->FastTrackFallback",
            parse_warning="seed|pdf_visual_timeout_fallback_fasttrack",
        ),
    )

    async def _parse_attempt_runner(**kwargs):
        raise RuntimeError("vision failed")

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            file_bytes=b"pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"pdf",
            parse_track="VisualTrack",
            parse_timeout_sec=70.0,
            parse_source_file_name=None,
            parse_source_file_bytes=None,
            progress_message="parsing",
            progress_extra={},
            resolve_parse_progress_ramp_sec=lambda **kwargs: 20.0,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=lambda parsed: parsed,
            visual_parse_policy_runtime=policy_runtime,
            parse_fallback_coordinator_runtime=fallback_runtime,
            docx_native_recovery_runtime=object(),
            fasttrack_fallback_runtime=object(),
            word_suffix=".pdf",
            original_file_is_word=False,
            visual_chain_required=True,
            docx_native_recovery_enabled=False,
            visual_strict=True,
            disable_fasttrack_fallback=False,
            nonpdf_total_budget_sec=None,
            started_at_sec=10.0,
            nonpdf_guard_sec=2.0,
            current_parse_warning="seed",
        )

    outcome = asyncio.run(_run())
    assert outcome.marked_markdown == "md-fast"
    assert outcome.parse_track == "VisualTrack->FastTrackFallback"
    assert outcome.parse_warning == "seed|pdf_visual_timeout_fallback_fasttrack"
    assert policy_runtime.exception_calls[0]["message"] == "vision failed"
    assert fallback_runtime.fasttrack_calls[0]["fallback_context_label"] == "demo:FastTrackFallback"


def test_document_parse_recovery_runtime_raises_terminal_http_exception() -> None:
    runtime = DocumentParseRecoveryRuntime(perf_counter=lambda: 40.0)
    policy_runtime = _PolicyRuntime(
        timeout_decision=SimpleNamespace(
            terminal_status_code=503,
            terminal_detail="visual chain required",
            docx_native_recovery_reason="",
            try_docx_native_recovery=False,
            should_attempt_fasttrack_fallback=False,
            fallback_timeout_sec=None,
            fallback_context_label="",
            fallback_track="",
            fallback_hint="",
            native_timeout_detail="",
        )
    )

    async def _parse_attempt_runner(**kwargs):
        raise TimeoutError("slow")

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            file_bytes=b"pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"pdf",
            parse_track="VisualTrack",
            parse_timeout_sec=60.0,
            parse_source_file_name=None,
            parse_source_file_bytes=None,
            progress_message="parsing",
            progress_extra={},
            resolve_parse_progress_ramp_sec=lambda **kwargs: 20.0,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=lambda parsed: parsed,
            visual_parse_policy_runtime=policy_runtime,
            parse_fallback_coordinator_runtime=_FallbackCoordinator(),
            docx_native_recovery_runtime=object(),
            fasttrack_fallback_runtime=object(),
            word_suffix=".pdf",
            original_file_is_word=False,
            visual_chain_required=True,
            docx_native_recovery_enabled=False,
            visual_strict=False,
            disable_fasttrack_fallback=False,
            nonpdf_total_budget_sec=None,
            started_at_sec=11.0,
            nonpdf_guard_sec=2.0,
            current_parse_warning="",
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "visual chain required"
