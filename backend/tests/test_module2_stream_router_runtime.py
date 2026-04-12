from __future__ import annotations

import hashlib
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


stream_router_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "stream_router_runtime.py"],
    "_smart_doc_flow_module2_stream_router_runtime",
)

StreamRouterRuntime = stream_router_runtime_module.StreamRouterRuntime


def test_stream_router_runtime_returns_cache_hit_when_cached_payload_exists() -> None:
    file_bytes = b"cached-payload"
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    version = "cache-version-1"
    schema_hash = "schema-1"
    expected_cache_key = hashlib.sha256(f"{version}:{file_hash}:{schema_hash}".encode("utf-8")).hexdigest()
    cached_payload = {"result": {"ok": True}}

    async def _check_cache(cache_key: str):
        assert cache_key == expected_cache_key
        return cached_payload

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: version,
    )

    async def _run():
        return await runtime.triage("report.pdf", file_bytes, schema_hash)

    import asyncio

    decision = asyncio.run(_run())
    assert decision.file_hash == file_hash
    assert decision.cache_key == expected_cache_key
    assert decision.track == "CacheHit"
    assert decision.cached_payload == cached_payload


def test_stream_router_runtime_skips_degraded_cached_payload_by_default() -> None:
    degraded_payload = {
        "result": {"a": {"value": "1"}},
        "diagnostics": {"quality_status": "degraded", "quality_target_field_count": 12},
        "soft_warnings": ["table_extract_error: RuntimeError: llm provider http error 429"],
    }

    async def _check_cache(_cache_key: str):
        return degraded_payload

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: "version-1",
    )

    async def _run():
        return await runtime.triage("notes.docx", b"docx-bytes", "schema-1")

    import asyncio

    decision = asyncio.run(_run())
    assert decision.track == "FastTrack"
    assert decision.cached_payload is None


def test_stream_router_runtime_allows_degraded_cache_when_env_enabled() -> None:
    degraded_payload = {
        "result": {"a": {"value": "1"}},
        "diagnostics": {"quality_status": "degraded"},
        "soft_warnings": ["table_extract_error: RuntimeError: llm provider http error 429"],
    }

    async def _check_cache(_cache_key: str):
        return degraded_payload

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: "version-1",
        getenv=lambda name, default="": "true" if name == "MODULE2_ALLOW_DEGRADED_CACHE_RESTORE" else default,
    )

    async def _run():
        return await runtime.triage("notes.docx", b"docx-bytes", "schema-1")

    import asyncio

    decision = asyncio.run(_run())
    assert decision.track == "CacheHit"
    assert decision.cached_payload == degraded_payload


def test_stream_router_runtime_routes_non_pdf_to_fasttrack() -> None:
    async def _check_cache(cache_key: str):
        return None

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: "version-1",
    )

    async def _run():
        return await runtime.triage("notes.docx", b"docx-bytes", "schema-1")

    import asyncio

    decision = asyncio.run(_run())
    assert decision.track == "FastTrack"
    assert decision.cached_payload is None


def test_stream_router_runtime_defaults_pdf_to_visualtrack() -> None:
    async def _check_cache(cache_key: str):
        return None

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: "version-1",
        getenv=lambda name, default="": default,
    )

    async def _run():
        return await runtime.triage("paper.pdf", b"%PDF-1.7 sample", "schema-1")

    import asyncio

    decision = asyncio.run(_run())
    assert decision.track == "VisualTrack"


def test_stream_router_runtime_detects_native_pdf_when_force_visual_disabled() -> None:
    async def _check_cache(cache_key: str):
        return None

    runtime = StreamRouterRuntime(
        check_cache=_check_cache,
        current_extraction_cache_version=lambda: "version-1",
        getenv=lambda name, default="": "false" if name == "MODULE2_PDF_FORCE_VISUAL" else default,
    )

    native_pdf_bytes = b"%PDF-1.7\n/Font\nBT Hello ET\n"

    async def _run():
        return await runtime.triage("native.pdf", native_pdf_bytes, "schema-1")

    import asyncio

    decision = asyncio.run(_run())
    assert decision.track == "FastTrack"
