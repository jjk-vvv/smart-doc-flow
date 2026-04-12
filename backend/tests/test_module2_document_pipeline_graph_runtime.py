from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace


document_pipeline_graph_runtime_module = importlib.import_module("module2.app.core.pipeline.document_pipeline_stages_runtime")
DocumentPipelineGraphRuntime = document_pipeline_graph_runtime_module.DocumentPipelineGraphRuntime


class _Logger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def info(self, message: str, *args) -> None:
        self.calls.append((message, args))


class _ExtractionGraphRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
            extract_ms=234,
            used_quick_fallback=False,
        )


def test_document_pipeline_graph_runtime_executes_graph_handoff() -> None:
    runtime = DocumentPipelineGraphRuntime()
    extraction_graph_runtime = _ExtractionGraphRuntime()
    logger = _Logger()

    async def _emit_progress(*args, **kwargs):
        return None

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            marked_markdown="markdown",
            bbox_map={"r1": [1.0]},
            table_blocks=[{"table_id": "t1"}],
            effective_schema={"fields": {"amount": {"type": "number"}}},
            effective_schema_fields={"amount": {"type": "number"}},
            figure_blocks=[{"figure_id": "f1"}],
            max_retries=2,
            extract_timeout_sec=210.0,
            schema_meta={"source": "auto"},
            extraction_graph_runtime=extraction_graph_runtime,
            run_graph=lambda state: state,
            extraction_llm_semaphore=SimpleNamespace(),
            emit_progress=_emit_progress,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            resolve_extract_progress_ramp_sec=lambda **kwargs: 1.0,
            quick_extract_from_tables=lambda **kwargs: {},
            disable_quick_table_fallback=lambda: False,
            logger=logger,
        )
    )

    assert extraction_graph_runtime.calls[0]["file_name"] == "demo.docx"
    assert extraction_graph_runtime.calls[0]["effective_schema_fields"] == {"amount": {"type": "number"}}
    assert outcome.final_state["results"] == {"amount": {"value": 100}}
    assert outcome.extract_ms == 234
    assert outcome.used_quick_fallback is False
    assert len(logger.calls) == 1
