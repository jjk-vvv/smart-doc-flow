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


docx_native_recovery_runtime_module = _load_module(
    ["module2", "app", "core", "format", "docx_native_recovery_runtime.py"],
    "_smart_doc_flow_module2_docx_native_recovery_runtime",
)

DocxNativeRecoveryRuntime = docx_native_recovery_runtime_module.DocxNativeRecoveryRuntime


def test_docx_native_recovery_runtime_skips_when_not_docx_or_disabled() -> None:
    runtime = DocxNativeRecoveryRuntime()

    async def _parse_attempt(**kwargs):
        raise AssertionError("parse_attempt should not be called")

    def _unpack_parse_output(parsed):
        raise AssertionError("unpack_parse_output should not be called")

    async def _run() -> tuple[object, object]:
        not_docx = await runtime.try_recover(
            file_name="report.pdf",
            file_bytes=b"pdf",
            reason="timeout",
            enabled=True,
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
        )
        disabled = await runtime.try_recover(
            file_name="report.docx",
            file_bytes=b"docx",
            reason="timeout",
            enabled=False,
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
        )
        return not_docx, disabled

    not_docx, disabled = asyncio.run(_run())
    assert not_docx is None
    assert disabled is None


def test_docx_native_recovery_runtime_skips_when_budget_exhausted() -> None:
    runtime = DocxNativeRecoveryRuntime()

    async def _parse_attempt(**kwargs):
        raise AssertionError("parse_attempt should not be called when budget is exhausted")

    def _unpack_parse_output(parsed):
        raise AssertionError("unpack_parse_output should not be called when budget is exhausted")

    async def _run():
        return await runtime.try_recover(
            file_name="report.docx",
            file_bytes=b"docx",
            reason="timeout",
            enabled=True,
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
            nonpdf_total_budget_sec=40.0,
            elapsed_sec=28.0,
            nonpdf_guard_sec=4.0,
        )

    assert asyncio.run(_run()) is None


def test_docx_native_recovery_runtime_runs_parse_attempt_and_patches_stats() -> None:
    runtime = DocxNativeRecoveryRuntime(
        getenv=lambda name, default="": "150" if name == "MODULE2_DOCX_NATIVE_RECOVERY_TIMEOUT_SEC" else default
    )
    captured: dict[str, object] = {}

    async def _parse_attempt(**kwargs):
        captured.update(kwargs)
        return ("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"native": True})

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.try_recover(
            file_name="report.docx",
            file_bytes=b"docx-bytes",
            reason="word_pdf_parse_timeout",
            enabled=True,
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
            timeout_hint_sec=120.0,
            nonpdf_total_budget_sec=180.0,
            elapsed_sec=20.0,
            nonpdf_guard_sec=2.0,
        )

    result = asyncio.run(_run())
    assert captured == {
        "attempt_file_bytes": b"docx-bytes",
        "attempt_file_name": "report.docx",
        "attempt_track": "NativeDocx",
        "attempt_timeout_sec": 120.0,
        "context_label": "report.docx:NativeDocx",
    }
    assert result == (
        "md",
        {"r1": [1.0]},
        [{"table_id": "t1"}],
        [{"figure_id": "f1"}],
        {
            "native": True,
            "docx_native_recovery": True,
            "docx_native_recovery_reason": "word_pdf_parse_timeout",
            "docx_native_recovery_timeout_sec": 120.0,
        },
    )
