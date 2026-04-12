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


cached_restore_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "cached_extraction_restore_runtime.py"],
    "_smart_doc_flow_module2_cached_extraction_restore_runtime",
)

CachedExtractionRestoreRuntime = cached_restore_runtime_module.CachedExtractionRestoreRuntime


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


def test_cached_extraction_restore_runtime_restores_payload_and_rebuilds_assistant_artifact() -> None:
    runtime = CachedExtractionRestoreRuntime()
    persist_calls: list[dict[str, Any]] = []

    response = runtime.restore_response(
        file_name="demo.pdf",
        file_hash="hash123",
        default_track="VisualTrack",
        cached_payload={
            "result": {"amount": {"value": 100}},
            "errors": ["oops", 42],
            "soft_warnings": ["seed", "seed"],
            "trace_hits": [{"object_type": "field"}],
            "trace_stats": {"trace_hit_count": 1},
            "track": "CachedTrack",
            "diagnostics": {"visual_mode": "layout"},
            "tables": [{"table_id": "t1"}],
            "figures": [],
        },
        normalize_soft_warnings=lambda value: list(dict.fromkeys(str(item) for item in value if str(item).strip())),
        promote_visual_diagnostics=lambda payload: {**payload, "promoted": True},
        persist_assistant_payload_artifact=lambda **kwargs: (
            persist_calls.append(dict(kwargs)) or ("assistant_payload/hash123/payload.json", "/extract/artifact/payload")
        ),
        extraction_result_factory=lambda payload: {"wrapped": payload},
        document_response_factory=lambda **kwargs: _FakeResponse(**kwargs),
    )

    assert response.file_name == "demo.pdf"
    assert response.file_hash == "hash123"
    assert response.track == "CachedTrack"
    assert response.cached is True
    assert response.result == {"wrapped": {"amount": {"value": 100}}}
    assert response.errors == ["oops", "42"]
    assert response.soft_warnings == ["seed"]
    assert response.trace_hits == [{"object_type": "field"}]
    assert response.trace_stats == {"trace_hit_count": 1}
    assert response.diagnostics["promoted"] is True
    assert response.diagnostics["assistant_payload_artifact_path"] == "assistant_payload/hash123/payload.json"
    assert response.diagnostics["assistant_payload_version"] == "module2-assistant-payload-v1"
    assert persist_calls[0]["file_name"] == "demo.pdf"


def test_cached_extraction_restore_runtime_falls_back_to_metrics_and_skips_rebuild_when_present() -> None:
    runtime = CachedExtractionRestoreRuntime()
    persist_calls: list[dict[str, Any]] = []

    response = runtime.restore_response(
        file_name="demo.txt",
        file_hash="hash456",
        default_track="FastTrack",
        cached_payload={
            "result": "invalid",
            "errors": "invalid",
            "soft_warnings": "invalid",
            "trace_hits": {"bad": True},
            "trace_stats": [],
            "metrics": {"assistant_payload_artifact_path": "existing.json"},
        },
        normalize_soft_warnings=lambda value: [],
        promote_visual_diagnostics=lambda payload: dict(payload),
        persist_assistant_payload_artifact=lambda **kwargs: (
            persist_calls.append(dict(kwargs)) or ("", "")
        ),
        extraction_result_factory=lambda payload: payload,
        document_response_factory=lambda **kwargs: _FakeResponse(**kwargs),
    )

    assert response.track == "FastTrack"
    assert response.result == {}
    assert response.errors == []
    assert response.soft_warnings == []
    assert response.trace_hits == []
    assert response.trace_stats == {}
    assert response.diagnostics["assistant_payload_artifact_path"] == "existing.json"
    assert persist_calls == []
