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
    ["module2", "app", "core", "pipeline", "document_flow_runtime.py"],
    "_smart_doc_flow_module2_document_flow_runtime_for_workflow",
)

DocumentWorkflowRuntime = document_flow_runtime_module.DocumentWorkflowRuntime


class _PerfCounter:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        if len(self._values) == 1:
            return self._values[0]
        return self._values.pop(0)


class _ExecutionRuntime:
    def __init__(self, *, cached_response=None) -> None:
        self.cached_response = cached_response
        self.start_calls: list[dict[str, object]] = []
        self.finalize_calls: list[dict[str, object]] = []
        self.progress_events: list[tuple[str, float, str, dict[str, object]]] = []

    async def start(self, **kwargs):
        self.start_calls.append(dict(kwargs))

        async def _emit_progress(stage, ratio, message="", extra=None):
            self.progress_events.append((stage, ratio, message, dict(extra or {})))

        return SimpleNamespace(
            decision=SimpleNamespace(file_hash="hash123", cache_key="cache123", track="VisualTrack"),
            emit_progress=_emit_progress,
            cached_response=self.cached_response,
        )

    async def finalize_success(self, **kwargs):
        self.finalize_calls.append(dict(kwargs))
        await kwargs["emit_progress"]("completed", 1.0, "抽取完成")
        return {"response": "ok", "cache_key": kwargs["cache_key"]}


class _PipelineRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            parse_track="VisualTrack",
            parse_ms=120,
            extract_ms=240,
            parse_warning="warning",
            parse_timeout_sec=90.0,
            extract_timeout_sec=180.0,
            nonpdf_total_budget_sec=150.0,
            word_parse_via_pdf=True,
            word_parse_extract_budget_sec=60.0,
            word_convert_budget_sec=30.0,
            dynamic_extract_timeout_meta={"boost": True},
            schema_meta={"source": "auto"},
            allow_schema_llm=True,
            schema_context_preview="schema preview",
            file_size_mb=0.5,
            naming_template="finance_document",
            used_quick_fallback=False,
            chain_contract={"required": True, "satisfied": True},
            final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
            effective_schema_fields={"amount": {"type": "number"}},
            marked_markdown="markdown",
            bbox_map={"r1": [1.0]},
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            conversion_diag={"office_pdf_converted": True},
            parse_stats={"pipeline": "visual_first"},
            nonpdf_preflight={"profile": "mixed"},
            nonpdf_budget={"parse_timeout_sec": 60.0},
        )


class _PostprocessRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_pipeline_response_bundle(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(response={"document": "ok"}, cache_payload={"cache_key": kwargs["cache_key"]})


def test_document_workflow_runtime_short_circuits_cached_response() -> None:
    execution_runtime = _ExecutionRuntime(cached_response={"cached": True})
    pipeline_runtime = _PipelineRuntime()
    postprocess_runtime = _PostprocessRuntime()
    runtime = DocumentWorkflowRuntime(
        document_execution_runtime=execution_runtime,
        document_pipeline_runtime=pipeline_runtime,
        document_postprocess_runtime=postprocess_runtime,
        perf_counter=_PerfCounter([100.0]),
    )

    response = asyncio.run(
        runtime.execute(
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            schema={"fields": {}},
            schema_hash="schema123",
            max_retries=1,
            progress_hook=None,
        )
    )

    assert response == {"cached": True}
    assert len(execution_runtime.start_calls) == 1
    assert pipeline_runtime.calls == []
    assert postprocess_runtime.calls == []
    assert execution_runtime.finalize_calls == []


def test_document_workflow_runtime_coordinates_post_pipeline_finalize() -> None:
    execution_runtime = _ExecutionRuntime()
    pipeline_runtime = _PipelineRuntime()
    postprocess_runtime = _PostprocessRuntime()
    runtime = DocumentWorkflowRuntime(
        document_execution_runtime=execution_runtime,
        document_pipeline_runtime=pipeline_runtime,
        document_postprocess_runtime=postprocess_runtime,
        perf_counter=_PerfCounter([100.0, 100.75]),
    )

    response = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            schema={"fields": {"amount": {"type": "number"}}},
            schema_hash="schema456",
            max_retries=2,
            progress_hook=None,
        )
    )

    assert response == {"response": "ok", "cache_key": "cache123"}
    assert execution_runtime.start_calls[0]["file_name"] == "demo.docx"
    assert pipeline_runtime.calls[0]["file_hash"] == "hash123"
    assert pipeline_runtime.calls[0]["initial_track"] == "VisualTrack"
    assert postprocess_runtime.calls[0]["schema_hash"] == "schema456"
    assert postprocess_runtime.calls[0]["total_ms"] == 750
    assert postprocess_runtime.calls[0]["pipeline_outcome"].nonpdf_preflight == {"profile": "mixed"}
    assert execution_runtime.finalize_calls[0]["cache_key"] == "cache123"
    assert execution_runtime.finalize_calls[0]["response_bundle"].cache_payload == {"cache_key": "cache123"}
    assert execution_runtime.progress_events == [
        ("finalizing", 0.96, "抽取完成，正在整理结果与缓存", {}),
        ("completed", 1.0, "抽取完成", {}),
    ]
