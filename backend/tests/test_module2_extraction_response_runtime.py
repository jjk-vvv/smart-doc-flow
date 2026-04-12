from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


extraction_response_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_postprocess_runtime.py"],
    "_smart_doc_flow_module2_extraction_response_runtime",
)

ExtractionResponseRuntime = extraction_response_runtime_module.ExtractionResponseRuntime


class _ModelDumpWrapper:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def model_dump(self, mode: str = "python") -> Any:
        assert mode == "json"
        return self.payload


@dataclass
class _FakeResponse:
    file_name: str
    file_hash: str
    track: str
    cached: bool
    result: Any
    errors: list[str]
    soft_warnings: list[str]
    trace_hits: list[Any]
    trace_stats: dict[str, Any]
    diagnostics: dict[str, Any]


def test_extraction_response_runtime_builds_response_and_cache_payload() -> None:
    runtime = ExtractionResponseRuntime()

    bundle = runtime.build_bundle(
        file_name="demo.pdf",
        file_hash="hash123",
        schema_hash="schema123",
        cache_key="cache123",
        track="VisualTrack",
        cached=False,
        final_results={"amount": {"value": 100}},
        final_errors=["warning"],
        soft_warnings=["soft"],
        trace_hits=[_ModelDumpWrapper({"object_type": "field"}), {"object_type": "table"}],
        trace_stats={"trace_hit_count": 2},
        diagnostics={"ok": True},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        extraction_result_factory=lambda payload: _ModelDumpWrapper(payload),
        document_response_factory=lambda **kwargs: _FakeResponse(**kwargs),
    )

    response = bundle.response
    assert response.file_name == "demo.pdf"
    assert response.track == "VisualTrack"
    assert isinstance(response.result, _ModelDumpWrapper)
    assert bundle.cache_payload["file_hash"] == "hash123"
    assert bundle.cache_payload["schema_hash"] == "schema123"
    assert bundle.cache_payload["cache_key"] == "cache123"
    assert bundle.cache_payload["result"] == {"amount": {"value": 100}}
    assert bundle.cache_payload["trace_hits"] == [
        {"object_type": "field"},
        {"object_type": "table"},
    ]
    assert bundle.cache_payload["metrics"] == {"ok": True}
    assert bundle.cache_payload["tables"] == [{"table_id": "t1"}]
    assert bundle.cache_payload["figures"] == [{"figure_id": "f1"}]


def test_extraction_response_runtime_passes_through_plain_payloads_without_model_dump() -> None:
    runtime = ExtractionResponseRuntime()

    bundle = runtime.build_bundle(
        file_name="demo.txt",
        file_hash="hash456",
        schema_hash="schema456",
        cache_key="cache456",
        track="FastTrack",
        cached=True,
        final_results={"title": "hello"},
        final_errors=[],
        soft_warnings=[],
        trace_hits=[{"object_type": "field"}],
        trace_stats={},
        diagnostics={"cached": True},
        table_blocks=[],
        figure_blocks=[],
        extraction_result_factory=lambda payload: payload,
        document_response_factory=lambda **kwargs: _FakeResponse(**kwargs),
    )

    assert bundle.response.cached is True
    assert bundle.cache_payload["cached"] is True
    assert bundle.cache_payload["result"] == {"title": "hello"}
    assert bundle.cache_payload["trace_hits"] == [{"object_type": "field"}]
