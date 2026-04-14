from __future__ import annotations

import importlib.util
import asyncio
import sys
from pathlib import Path

import pytest


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


fasttrack_fallback_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_parse_recovery_runtime.py"],
    "_smart_doc_flow_module2_document_parse_recovery_runtime_for_fasttrack_fallback",
)

FastTrackFallbackRuntime = fasttrack_fallback_runtime_module.FastTrackFallbackRuntime


def test_fasttrack_fallback_runtime_runs_parse_attempt_and_unpacks_result() -> None:
    runtime = FastTrackFallbackRuntime()
    captured: dict[str, object] = {}

    async def _parse_attempt(**kwargs):
        captured.update(kwargs)
        return ("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.run_fasttrack_fallback(
            file_name="demo.pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            fallback_timeout_sec=42.0,
            fallback_context_label="demo:FastTrackFallback",
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
            native_timeout_detail="Native parsing timed out for demo.pdf",
            parse_source_file_name="source.docx",
            parse_source_file_bytes=b"docx",
        )

    result = asyncio.run(_run())
    assert result[0] == "md"
    assert captured == {
        "attempt_file_bytes": b"%PDF",
        "attempt_file_name": "demo.pdf",
        "attempt_track": "FastTrack",
        "attempt_timeout_sec": 42.0,
        "context_label": "demo:FastTrackFallback",
        "attempt_source_file_name": "source.docx",
        "attempt_source_file_bytes": b"docx",
    }


def test_fasttrack_fallback_runtime_maps_timeout_to_http_504() -> None:
    runtime = FastTrackFallbackRuntime()

    async def _parse_attempt(**kwargs):
        raise TimeoutError("slow fallback")

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.run_fasttrack_fallback(
            file_name="demo.pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            fallback_timeout_sec=42.0,
            fallback_context_label="demo:FastTrackFallback",
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
            native_timeout_detail="Native parsing timed out for demo.pdf",
        )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(_run())

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 504
    assert getattr(exc, "detail", None) == "Native parsing timed out for demo.pdf"


def test_fasttrack_fallback_runtime_maps_unsupported_type_to_http_400() -> None:
    runtime = FastTrackFallbackRuntime()

    async def _parse_attempt(**kwargs):
        raise ValueError("Unsupported file type: .bin")

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.run_fasttrack_fallback(
            file_name="demo.bin",
            parse_input_name="demo.bin",
            parse_input_bytes=b"bin",
            fallback_timeout_sec=20.0,
            fallback_context_label="demo:FastTrackFallback",
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
        )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(_run())

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 400
    assert getattr(exc, "detail", None) == "Unsupported file type: .bin"


def test_fasttrack_fallback_runtime_maps_generic_failure_to_http_500() -> None:
    runtime = FastTrackFallbackRuntime()

    async def _parse_attempt(**kwargs):
        raise RuntimeError("boom")

    def _unpack_parse_output(parsed):
        return parsed

    async def _run():
        return await runtime.run_fasttrack_fallback(
            file_name="demo.pdf",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            fallback_timeout_sec=20.0,
            fallback_context_label="demo:FastTrackFallback",
            parse_attempt=_parse_attempt,
            unpack_parse_output=_unpack_parse_output,
        )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(_run())

    exc = exc_info.value
    assert getattr(exc, "status_code", None) == 500
    assert getattr(exc, "detail", None) == "Native parsing failed for demo.pdf: boom"
