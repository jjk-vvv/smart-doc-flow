from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from pathlib import Path

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


extraction_graph_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "extraction_graph_runtime.py"],
    "_smart_doc_flow_module2_extraction_graph_runtime",
)

ExtractionGraphRuntime = extraction_graph_runtime_module.ExtractionGraphRuntime


def test_extraction_graph_runtime_runs_graph_successfully() -> None:
    runtime = ExtractionGraphRuntime(perf_counter=lambda: 10.0)
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def _llm_semaphore():
        captured["semaphore_entered"] = True
        yield

    async def _emit_progress(stage, ratio, message="", extra=None):
        captured["progress"] = {
            "stage": stage,
            "ratio": ratio,
            "message": message,
            "extra": extra,
        }

    async def _run_graph(init_state):
        captured["init_state"] = dict(init_state)
        return {
            "results": {"amount": {"value": 100}},
            "errors": [],
            "soft_warnings": [],
        }

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        captured["heartbeat_kwargs"] = dict(kwargs)
        return await awaitable

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            markdown="markdown",
            bbox_map={"r1": [1.0]},
            table_blocks=[{"table_id": "t1"}],
            effective_schema={"fields": {"amount": {"type": "number"}}},
            effective_schema_fields={"amount": {"type": "number"}},
            figure_blocks=[{"figure_id": "f1"}],
            max_retries=3,
            extract_timeout_sec=40.0,
            schema_meta={"mode": "manual"},
            run_graph=_run_graph,
            extraction_llm_semaphore=_llm_semaphore(),
            emit_progress=_emit_progress,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=lambda **kwargs: 18.0,
            quick_extract_from_tables=lambda **kwargs: {},
            disable_quick_table_fallback=lambda: False,
        )

    outcome = asyncio.run(_run())
    assert outcome.final_state["results"] == {"amount": {"value": 100}}
    assert outcome.extract_ms == 0
    assert outcome.used_quick_fallback is False
    assert captured["progress"]["stage"] == "extracting"
    assert captured["init_state"]["max_retries"] == 3
    assert captured["heartbeat_kwargs"]["ceiling_ratio"] == 0.93


def test_extraction_graph_runtime_uses_quick_fallback_on_auto_schema_timeout() -> None:
    runtime = ExtractionGraphRuntime(perf_counter=lambda: 5.0)

    @asynccontextmanager
    async def _llm_semaphore():
        yield

    async def _run_graph(init_state):
        raise TimeoutError("slow")

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            markdown="markdown",
            bbox_map={},
            table_blocks=[{"table_id": "t1"}],
            effective_schema={"fields": {"amount": {"type": "number"}}},
            effective_schema_fields={"amount": {"type": "number"}},
            figure_blocks=[],
            max_retries=2,
            extract_timeout_sec=20.0,
            schema_meta={"mode": "auto"},
            run_graph=_run_graph,
            extraction_llm_semaphore=_llm_semaphore(),
            emit_progress=_emit_progress,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=lambda **kwargs: 12.0,
            quick_extract_from_tables=lambda **kwargs: {"amount": {"value": 88}},
            disable_quick_table_fallback=lambda: False,
        )

    outcome = asyncio.run(_run())
    assert outcome.used_quick_fallback is True
    assert outcome.final_state["results"] == {"amount": {"value": 88}}
    assert outcome.final_state["soft_warnings"] == ["quick_table_fallback:Extraction timed out for demo.pdf"]


def test_extraction_graph_runtime_raises_when_quick_fallback_is_disabled() -> None:
    runtime = ExtractionGraphRuntime(perf_counter=lambda: 5.0)

    @asynccontextmanager
    async def _llm_semaphore():
        yield

    async def _run_graph(init_state):
        raise TimeoutError("slow")

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            markdown="markdown",
            bbox_map={},
            table_blocks=[],
            effective_schema={"fields": {}},
            effective_schema_fields={},
            figure_blocks=[],
            max_retries=1,
            extract_timeout_sec=20.0,
            schema_meta={"mode": "auto"},
            run_graph=_run_graph,
            extraction_llm_semaphore=_llm_semaphore(),
            emit_progress=_emit_progress,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=lambda **kwargs: 12.0,
            quick_extract_from_tables=lambda **kwargs: {},
            disable_quick_table_fallback=lambda: True,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 504
    assert "quick table fallback is disabled" in exc_info.value.detail


def test_extraction_graph_runtime_wraps_graph_exception() -> None:
    runtime = ExtractionGraphRuntime(perf_counter=lambda: 5.0)

    @asynccontextmanager
    async def _llm_semaphore():
        yield

    async def _run_graph(init_state):
        raise RuntimeError("boom")

    async def _run_with_progress_heartbeat(awaitable, **kwargs):
        return await awaitable

    async def _emit_progress(*args, **kwargs):
        return None

    async def _run():
        return await runtime.execute(
            file_name="demo.pdf",
            markdown="markdown",
            bbox_map={},
            table_blocks=[],
            effective_schema={"fields": {}},
            effective_schema_fields={},
            figure_blocks=[],
            max_retries=1,
            extract_timeout_sec=20.0,
            schema_meta={"mode": "manual"},
            run_graph=_run_graph,
            extraction_llm_semaphore=_llm_semaphore(),
            emit_progress=_emit_progress,
            run_with_progress_heartbeat=_run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=lambda **kwargs: 12.0,
            quick_extract_from_tables=lambda **kwargs: {},
            disable_quick_table_fallback=lambda: False,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Extraction graph failed for demo.pdf: boom"
