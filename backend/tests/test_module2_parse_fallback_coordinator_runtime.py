from __future__ import annotations

import asyncio
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


parse_fallback_coordinator_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_parse_recovery_runtime.py"],
    "_smart_doc_flow_module2_document_parse_recovery_runtime_for_fallback_coordinator",
)

ParseFallbackCoordinatorRuntime = parse_fallback_coordinator_runtime_module.ParseFallbackCoordinatorRuntime


class _RecoveryRuntime:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def try_recover(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return self.result


class _FasttrackRuntime:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def run_fasttrack_fallback(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.result


def _append_warning(current_warning, warning: str) -> str:
    current = str(current_warning or "").strip()
    fragment = str(warning or "").strip()
    return fragment if not current else f"{current}|{fragment}"


def test_parse_fallback_coordinator_runtime_returns_recovery_outcome() -> None:
    runtime = ParseFallbackCoordinatorRuntime()
    recovery_runtime = _RecoveryRuntime(
        result=("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})
    )

    async def _parse_attempt_runner(**kwargs):
        return None

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.try_docx_native_recovery(
            file_name="demo.docx",
            file_bytes=b"docx",
            reason="word_pdf_visual_error",
            enabled=True,
            current_warning="seed",
            success_track="VisualTrack->NativeDocxRecovery",
            success_warning="word_pdf_visual_recovered_native_docx",
            append_warning=_append_warning,
            docx_native_recovery_runtime=recovery_runtime,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=_unpack_parse_output,
            timeout_hint_sec=32.0,
            nonpdf_total_budget_sec=90.0,
            elapsed_sec=10.0,
            nonpdf_guard_sec=2.0,
        )

    outcome = asyncio.run(_run())
    assert outcome.resolved is True
    assert outcome.parse_track == "VisualTrack->NativeDocxRecovery"
    assert outcome.parse_warning == "seed|word_pdf_visual_recovered_native_docx"
    assert outcome.result is not None
    assert recovery_runtime.calls[0]["reason"] == "word_pdf_visual_error"


def test_parse_fallback_coordinator_runtime_appends_recovery_failure_warning() -> None:
    runtime = ParseFallbackCoordinatorRuntime()
    recovery_runtime = _RecoveryRuntime(error=RuntimeError("boom"))

    async def _parse_attempt_runner(**kwargs):
        return None

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.try_docx_native_recovery(
            file_name="demo.docx",
            file_bytes=b"docx",
            reason="word_pdf_parse_timeout",
            enabled=True,
            current_warning="seed",
            success_track="VisualTrack->NativeDocxRecoveryTimeout",
            success_warning="word_pdf_parse_timeout_recovered_native_docx",
            append_warning=_append_warning,
            docx_native_recovery_runtime=recovery_runtime,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=_unpack_parse_output,
        )

    outcome = asyncio.run(_run())
    assert outcome.resolved is False
    assert outcome.parse_warning == "seed|docx_native_recovery_failed:RuntimeError"


def test_parse_fallback_coordinator_runtime_returns_fasttrack_fallback_outcome() -> None:
    runtime = ParseFallbackCoordinatorRuntime()
    fasttrack_runtime = _FasttrackRuntime(
        result=("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})
    )

    async def _parse_attempt_runner(**kwargs):
        return None

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.run_fasttrack_fallback(
            file_name="demo.pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            fallback_timeout_sec=42.0,
            fallback_context_label="demo:FastTrackFallback",
            current_warning="seed",
            success_track="VisualTrack->FastTrackFallback",
            success_warning="pdf_visual_timeout_fallback_fasttrack",
            append_warning=_append_warning,
            fasttrack_fallback_runtime=fasttrack_runtime,
            parse_attempt_runner=_parse_attempt_runner,
            unpack_parse_output=_unpack_parse_output,
            native_timeout_detail="Native parsing timed out for demo.pdf",
            parse_source_file_name="source.docx",
            parse_source_file_bytes=b"docx",
        )

    outcome = asyncio.run(_run())
    assert outcome.resolved is True
    assert outcome.parse_track == "VisualTrack->FastTrackFallback"
    assert outcome.parse_warning == "seed|pdf_visual_timeout_fallback_fasttrack"
    assert outcome.result is not None
    assert fasttrack_runtime.calls[0]["native_timeout_detail"] == "Native parsing timed out for demo.pdf"
