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


visual_vision_jobs_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_execution_runtime.py"],
    "_smart_doc_flow_module2_visual_vision_jobs",
)

VisualVisionJobsRuntime = visual_vision_jobs_module.VisualVisionJobsRuntime


class _FakeVision:
    def __init__(self) -> None:
        self.table_calls: list[dict[str, object]] = []
        self.figure_calls: list[dict[str, object]] = []
        self._table_failures_remaining = 0

    def extract_table(self, *, image_bytes: bytes, mime_type: str, context: dict[str, object]) -> dict[str, object]:
        self.table_calls.append(
            {
                "image_bytes": image_bytes,
                "mime_type": mime_type,
                "context": dict(context),
            }
        )
        if self._table_failures_remaining > 0:
            self._table_failures_remaining -= 1
            raise RuntimeError("timeout while calling vision backend")
        time.sleep(0.03)
        return {"kind": "table", "rows": [["2025", "12"]]}

    def extract_figure(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        context: dict[str, object],
        allow_refine: bool,
    ) -> dict[str, object]:
        self.figure_calls.append(
            {
                "image_bytes": image_bytes,
                "mime_type": mime_type,
                "context": dict(context),
                "allow_refine": allow_refine,
            }
        )
        return {"kind": "figure", "summary": "chart", "allow_refine": allow_refine}


def test_visual_vision_jobs_runtime_skips_extractor_when_vision_not_ready() -> None:
    runtime = VisualVisionJobsRuntime(visual_vision_concurrency=4)
    vision = _FakeVision()

    results = runtime.run_jobs(
        jobs=[
            {
                "index": 0,
                "kind": "table",
                "roi_bytes": b"table",
                "roi_mime": "image/png",
                "context": {"page": 1},
            }
        ],
        vision=vision,
        vision_ready=False,
    )

    assert results[0]["attempted"] is False
    assert results[0]["payload"] == {}
    assert vision.table_calls == []
    assert vision.figure_calls == []


def test_visual_vision_jobs_runtime_collects_parallel_results_by_index() -> None:
    runtime = VisualVisionJobsRuntime(visual_vision_concurrency=2)
    vision = _FakeVision()

    results = runtime.run_jobs(
        jobs=[
            {
                "index": 0,
                "kind": "table",
                "roi_bytes": b"table",
                "roi_mime": "image/png",
                "context": {"page": 1},
            },
            {
                "index": 1,
                "kind": "figure",
                "roi_bytes": b"figure",
                "roi_mime": "image/png",
                "context": {"page": 2},
                "allow_refine": True,
            },
        ],
        vision=vision,
        vision_ready=True,
    )

    assert results[0]["attempted"] is True
    assert results[0]["payload"]["kind"] == "table"
    assert results[1]["attempted"] is True
    assert results[1]["payload"]["kind"] == "figure"
    assert results[1]["payload"]["allow_refine"] is True
    assert vision.figure_calls[0]["allow_refine"] is True


def test_visual_vision_jobs_runtime_retries_retryable_transport_failures_serially() -> None:
    runtime = VisualVisionJobsRuntime(visual_vision_concurrency=1)
    vision = _FakeVision()
    vision._table_failures_remaining = 1

    results = runtime.run_jobs(
        jobs=[
            {
                "index": 0,
                "kind": "table",
                "roi_bytes": b"table",
                "roi_mime": "image/png",
                "context": {"page": 3},
            }
        ],
        vision=vision,
        vision_ready=True,
    )

    assert len(vision.table_calls) == 2
    assert results[0]["serial_recovery_retry"] is True
    assert results[0]["error"] == ""
    assert results[0]["payload"]["kind"] == "table"
