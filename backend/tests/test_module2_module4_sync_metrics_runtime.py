from __future__ import annotations

import importlib.util
import sys
import time
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


module4_sync_metrics_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "module4_sync_metrics_runtime.py"],
    "_smart_doc_flow_module2_module4_sync_metrics_runtime",
)

Module4SyncMetricsRuntime = module4_sync_metrics_runtime_module.Module4SyncMetricsRuntime


def test_module4_sync_metrics_runtime_marks_attempts() -> None:
    runtime = Module4SyncMetricsRuntime()

    runtime.mark_attempt()
    runtime.mark_attempt()

    snapshot = runtime.snapshot()
    assert snapshot["attempted_batches"] == 2
    assert snapshot["succeeded_batches"] == 0
    assert snapshot["failed_batches"] == 0


def test_module4_sync_metrics_runtime_marks_success() -> None:
    runtime = Module4SyncMetricsRuntime()

    runtime.mark_success(
        response_payload={"job_id": "job-1", "batch_id": "batch-1"},
        endpoint="/module4/ingest",
        source_batch_key="source-1",
    )

    snapshot = runtime.snapshot()
    assert snapshot["succeeded_batches"] == 1
    assert snapshot["last_error"] == ""
    assert snapshot["last_job_id"] == "job-1"
    assert snapshot["last_batch_id"] == "batch-1"
    assert snapshot["last_endpoint"] == "/module4/ingest"
    assert snapshot["last_source_batch_key"] == "source-1"
    assert float(snapshot["last_success_at"]) <= time.time()


def test_module4_sync_metrics_runtime_marks_failure() -> None:
    runtime = Module4SyncMetricsRuntime()
    long_error = "x" * 600

    runtime.mark_failure(
        message=long_error,
        endpoint="/module4/ingest",
        source_batch_key="source-2",
    )

    snapshot = runtime.snapshot()
    assert snapshot["failed_batches"] == 1
    assert snapshot["last_error"] == long_error[:400]
    assert snapshot["last_endpoint"] == "/module4/ingest"
    assert snapshot["last_source_batch_key"] == "source-2"
