from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
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


document_parse_attempt_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_pipeline_stages_runtime.py"],
    "_smart_doc_flow_module2_document_parse_attempt_runtime",
)

DocumentParseAttemptRuntime = document_parse_attempt_runtime_module.DocumentParseAttemptRuntime


def test_document_parse_attempt_runtime_unpacks_parse_output_shapes() -> None:
    runtime = DocumentParseAttemptRuntime()

    assert runtime.unpack_parse_output(("md", {"r1": [1.0]}, [{"table_id": "t1"}])) == (
        "md",
        {"r1": [1.0]},
        [{"table_id": "t1"}],
        [],
        {},
    )
    assert runtime.unpack_parse_output(("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}])) == (
        "md",
        {"r1": [1.0]},
        [{"table_id": "t1"}],
        [{"figure_id": "f1"}],
        {},
    )
    assert runtime.unpack_parse_output(
        ("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})
    ) == (
        "md",
        {"r1": [1.0]},
        [{"table_id": "t1"}],
        [{"figure_id": "f1"}],
        {"ok": True},
    )


def test_document_parse_attempt_runtime_rejects_invalid_parse_output_shape() -> None:
    runtime = DocumentParseAttemptRuntime()

    with pytest.raises(ValueError, match="Unexpected parse output shape"):
        runtime.unpack_parse_output(("only", "two"))


def test_document_parse_attempt_runtime_runs_without_heartbeat() -> None:
    runtime = DocumentParseAttemptRuntime()
    events: list[tuple[str, object]] = []

    @asynccontextmanager
    async def _slots(track: str):
        events.append(("enter", track))
        try:
            yield
        finally:
            events.append(("exit", track))

    async def _run_parse_in_process_pool(**kwargs):
        events.append(("pool", kwargs))
        return ("md", {}, [])

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        events.append(("heartbeat", kwargs))
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.run_parse_attempt(
            loop=object(),
            attempt_file_bytes=b"pdf",
            attempt_file_name="demo.pdf",
            attempt_track="VisualTrack",
            attempt_timeout_sec=33.0,
            context_label="demo:VisualTrack",
            acquire_parse_execution_slots=_slots,
            run_parse_in_process_pool=_run_parse_in_process_pool,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            emit_progress=_emit_progress,
        )

    result = asyncio.run(_run())
    assert result == ("md", {}, [])
    assert events[0] == ("enter", "VisualTrack")
    assert events[1][0] == "pool"
    assert events[1][1]["file_name"] == "demo.pdf"
    assert events[1][1]["timeout_sec"] == 33.0
    assert events[2] == ("exit", "VisualTrack")
    assert all(event[0] != "heartbeat" for event in events)


def test_document_parse_attempt_runtime_runs_with_heartbeat() -> None:
    runtime = DocumentParseAttemptRuntime()
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def _slots(track: str):
        yield

    async def _run_parse_in_process_pool(**kwargs):
        captured["pool_kwargs"] = kwargs
        return ("md", {"r1": [1.0]}, [{"table_id": "t1"}], [{"figure_id": "f1"}], {"ok": True})

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        captured["heartbeat_kwargs"] = kwargs
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.run_parse_attempt(
            loop="loop-token",
            attempt_file_bytes=b"pdf",
            attempt_file_name="demo.pdf",
            attempt_track="VisualTrack",
            attempt_timeout_sec=48.0,
            context_label="demo:VisualTrack",
            acquire_parse_execution_slots=_slots,
            run_parse_in_process_pool=_run_parse_in_process_pool,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            emit_progress=_emit_progress,
            attempt_source_file_name="source.docx",
            attempt_source_file_bytes=b"docx",
            heartbeat_stage="parsing",
            heartbeat_base_ratio=0.32,
            heartbeat_message="running parse",
            heartbeat_extra={"parse_track": "VisualTrack"},
            heartbeat_ceiling_ratio=0.74,
            heartbeat_ramp_sec=30.0,
        )

    result = asyncio.run(_run())
    assert result[0] == "md"
    assert captured["pool_kwargs"] == {
        "loop": "loop-token",
        "file_bytes": b"pdf",
        "file_name": "demo.pdf",
        "track": "VisualTrack",
        "timeout_sec": 48.0,
        "context_label": "demo:VisualTrack",
        "source_file_name": "source.docx",
        "source_file_bytes": b"docx",
    }
    assert captured["heartbeat_kwargs"]["stage"] == "parsing"
    assert captured["heartbeat_kwargs"]["base_ratio"] == 0.32
    assert captured["heartbeat_kwargs"]["message"] == "running parse"
    assert captured["heartbeat_kwargs"]["extra"] == {"parse_track": "VisualTrack"}
    assert captured["heartbeat_kwargs"]["ceiling_ratio"] == 0.74
    assert captured["heartbeat_kwargs"]["ramp_sec"] == 30.0


def test_document_parse_attempt_runtime_build_runner_reuses_bound_dependencies() -> None:
    runtime = DocumentParseAttemptRuntime()
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def _slots(track: str):
        captured["slot_track"] = track
        yield

    async def _run_parse_in_process_pool(**kwargs):
        captured["pool_kwargs"] = kwargs
        return ("md", {}, [])

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    runner = runtime.build_runner(
        loop="bound-loop",
        acquire_parse_execution_slots=_slots,
        run_parse_in_process_pool=_run_parse_in_process_pool,
        run_with_progress_heartbeat=_run_with_progress_heartbeat,
        emit_progress=_emit_progress,
    )

    async def _run():
        return await runner(
            attempt_file_bytes=b"pdf",
            attempt_file_name="bound.pdf",
            attempt_track="FastTrack",
            attempt_timeout_sec=21.0,
            context_label="bound:FastTrack",
        )

    result = asyncio.run(_run())
    assert result == ("md", {}, [])
    assert captured["slot_track"] == "FastTrack"
    assert captured["pool_kwargs"] == {
        "loop": "bound-loop",
        "file_bytes": b"pdf",
        "file_name": "bound.pdf",
        "track": "FastTrack",
        "timeout_sec": 21.0,
        "context_label": "bound:FastTrack",
        "source_file_name": None,
        "source_file_bytes": None,
    }
