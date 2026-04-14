from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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


document_flow_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_flow_runtime.py"],
    "_smart_doc_flow_module2_document_flow_runtime_for_execution",
)

DocumentExecutionRuntime = document_flow_runtime_module.DocumentExecutionRuntime
DocumentExecutionDependencyBundle = document_flow_runtime_module.DocumentExecutionDependencyBundle


class _CachedExtractionRestoreRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def restore_response(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"cached": True, "track": kwargs["default_track"]}


async def _save_extraction_result(cache_key: str, payload: dict[str, object]) -> None:
    _save_extraction_result.calls.append((cache_key, payload))


_save_extraction_result.calls = []


def _build_runtime(*, decision, cached_restore_runtime=None):
    restore_runtime = cached_restore_runtime or _CachedExtractionRestoreRuntime()
    return (
        DocumentExecutionRuntime(
            build_stream_router=lambda: SimpleNamespace(triage=lambda *_args: _triage(decision)),
            cached_extraction_restore_runtime=restore_runtime,
            normalize_soft_warnings=lambda value: value,
            promote_visual_diagnostics=lambda value: value,
            persist_assistant_payload_artifact=lambda **kwargs: ("", ""),
            extraction_result_factory=lambda payload: payload,
            document_response_factory=lambda **kwargs: kwargs,
            save_extraction_result=_save_extraction_result,
        ),
        restore_runtime,
    )


async def _triage(decision):
    return decision


def test_document_execution_runtime_restores_cached_response() -> None:
    progress_events: list[tuple[str, float, str, dict[str, object]]] = []
    decision = SimpleNamespace(
        file_hash="hash123",
        cache_key="cache123",
        track="CacheHit",
        cached_payload={"result": "cached"},
    )
    runtime, restore_runtime = _build_runtime(decision=decision)

    start = asyncio.run(
        runtime.start(
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            schema_hash="schema123",
            progress_hook=lambda stage, ratio, message, extra: _record_progress(progress_events, stage, ratio, message, extra),
        )
    )

    assert start.decision is decision
    assert start.cached_response == {"cached": True, "track": "CacheHit"}
    assert len(progress_events) == 1
    assert progress_events[0][0] == "cached"
    assert progress_events[0][1] == 1.0
    assert "cache" in progress_events[0][2].lower() or "缓存" in progress_events[0][2]
    assert progress_events[0][3] == {}
    assert len(restore_runtime.calls) == 1
    assert restore_runtime.calls[0]["file_name"] == "demo.pdf"
    assert restore_runtime.calls[0]["file_hash"] == "hash123"
    assert restore_runtime.calls[0]["default_track"] == "CacheHit"
    assert restore_runtime.calls[0]["cached_payload"] == {"result": "cached"}


def test_document_execution_runtime_emits_preflight_and_finalizes_success() -> None:
    _save_extraction_result.calls = []
    progress_events: list[tuple[str, float, str, dict[str, object]]] = []
    decision = SimpleNamespace(
        file_hash="hash456",
        cache_key="cache456",
        track="VisualTrack",
        cached_payload=None,
    )
    runtime, _ = _build_runtime(decision=decision)

    start = asyncio.run(
        runtime.start(
            file_name="demo.docx",
            file_bytes=b"docx",
            schema_hash="schema456",
            progress_hook=lambda stage, ratio, message, extra: _record_progress(progress_events, stage, ratio, message, extra),
        )
    )

    assert start.cached_response is None
    assert len(progress_events) == 1
    assert progress_events[0][0] == "preflight"
    assert progress_events[0][1] == 0.05
    assert "preflight" in progress_events[0][2].lower() or "预检查" in progress_events[0][2]
    assert progress_events[0][3] == {}

    response = asyncio.run(
        runtime.finalize_success(
            cache_key=decision.cache_key,
            response_bundle=SimpleNamespace(
                response={"ok": True},
                cache_payload={"cache_key": "cache456"},
            ),
            emit_progress=start.emit_progress,
        )
    )

    assert response == {"ok": True}
    assert _save_extraction_result.calls == [("cache456", {"cache_key": "cache456"})]
    assert len(progress_events) == 2
    assert progress_events[1][0] == "completed"
    assert progress_events[1][1] == 1.0
    assert "completed" in progress_events[1][2].lower() or "抽取完成" in progress_events[1][2]
    assert progress_events[1][3] == {}


def test_document_execution_runtime_swallows_progress_hook_errors() -> None:
    decision = SimpleNamespace(
        file_hash="hash789",
        cache_key="cache789",
        track="FastTrack",
        cached_payload=None,
    )
    runtime, _ = _build_runtime(decision=decision)

    async def _broken_progress(*_args, **_kwargs):
        raise RuntimeError("boom")

    start = asyncio.run(
        runtime.start(
            file_name="demo.txt",
            file_bytes=b"text",
            schema_hash="schema789",
            progress_hook=_broken_progress,
        )
    )

    assert start.cached_response is None


def test_document_execution_runtime_accepts_dependency_bundle() -> None:
    progress_events: list[tuple[str, float, str, dict[str, object]]] = []
    decision = SimpleNamespace(
        file_hash="hash-bundle",
        cache_key="cache-bundle",
        track="FastTrack",
        cached_payload=None,
    )
    restore_runtime = _CachedExtractionRestoreRuntime()
    runtime = DocumentExecutionRuntime(
        dependency_bundle=DocumentExecutionDependencyBundle(
            build_stream_router=lambda: SimpleNamespace(triage=lambda *_args: _triage(decision)),
            cached_extraction_restore_runtime=restore_runtime,
            normalize_soft_warnings=lambda value: value,
            promote_visual_diagnostics=lambda value: value,
            persist_assistant_payload_artifact=lambda **kwargs: ("", ""),
            extraction_result_factory=lambda payload: payload,
            document_response_factory=lambda **kwargs: kwargs,
            save_extraction_result=_save_extraction_result,
        )
    )

    start = asyncio.run(
        runtime.start(
            file_name="demo.txt",
            file_bytes=b"text",
            schema_hash="schema-bundle",
            progress_hook=lambda stage, ratio, message, extra: _record_progress(progress_events, stage, ratio, message, extra),
        )
    )

    assert start.cached_response is None
    assert start.decision.cache_key == "cache-bundle"
    assert len(progress_events) == 1
    assert progress_events[0][0] == "preflight"
    assert progress_events[0][1] == 0.05
    assert "preflight" in progress_events[0][2].lower() or "预检查" in progress_events[0][2]
    assert progress_events[0][3] == {}


async def _record_progress(events, stage, ratio, message, extra):
    events.append((stage, ratio, message, dict(extra)))
