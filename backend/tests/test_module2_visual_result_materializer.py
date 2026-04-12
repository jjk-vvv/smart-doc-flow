from __future__ import annotations

import importlib.util
import sys
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


visual_result_materializer_module = _load_module(
    ["module2", "app", "core", "visual", "visual_execution_runtime.py"],
    "_smart_doc_flow_module2_visual_result_materializer",
)

VisualResultMaterializerRuntime = visual_result_materializer_module.VisualResultMaterializerRuntime


def test_visual_result_materializer_runtime_materializes_index_zero_table_job() -> None:
    runtime = VisualResultMaterializerRuntime(
        table_cell_cap=10,
        build_table_from_visual_payload=lambda **kwargs: (
            {
                "table_id": kwargs["table_id"],
                "page": kwargs["page_no"],
                "source": kwargs["source"],
            },
            kwargs["emitted_cells"] + 1,
        ),
        table_payload_has_content=lambda payload: bool(payload.get("rows")),
        build_figure_from_visual_payload=lambda **kwargs: None,
        figure_payload_has_content=lambda payload: bool(payload.get("summary")),
    )

    result = runtime.materialize(
        vision_jobs=[
            {
                "index": 0,
                "kind": "table",
                "page_no": 1,
                "item": {"object_type": "table"},
            }
        ],
        vision_results={
            0: {
                "index": 0,
                "kind": "table",
                "payload": {"rows": [["2025", "12"]]},
                "attempted": True,
                "elapsed_ms": 7,
            }
        },
        parts=[],
        bbox_map={},
        page_dims={1: (100.0, 100.0)},
        runtime_table_max_per_page=1,
        runtime_figure_max_per_page=1,
        table_source="pdf_mineru_gemini",
        figure_source="pdf_mineru_gemini",
        vision_ready=True,
    )

    assert len(result["table_blocks"]) == 1
    assert result["table_blocks"][0]["table_id"] == "pdf_mineru_gemini_t1"
    assert result["table_blocks"][0]["vision_status"] == "attempted_success"
    assert result["vision_attempted_count"] == 1
    assert result["vision_success_count"] == 1
    assert result["vision_empty_count"] == 0


def test_visual_result_materializer_runtime_tracks_retry_success_and_page_caps() -> None:
    runtime = VisualResultMaterializerRuntime(
        table_cell_cap=10,
        build_table_from_visual_payload=lambda **kwargs: (
            {
                "table_id": kwargs["table_id"],
                "page": kwargs["page_no"],
                "source": kwargs["source"],
            },
            kwargs["emitted_cells"] + 1,
        ),
        table_payload_has_content=lambda payload: bool(payload.get("rows")),
        build_figure_from_visual_payload=lambda **kwargs: {
            "figure_id": kwargs["figure_id"],
            "page": kwargs["page_no"],
            "source": kwargs["source"],
        },
        figure_payload_has_content=lambda payload: bool(payload.get("summary")),
    )

    result = runtime.materialize(
        vision_jobs=[
            {
                "index": 0,
                "kind": "table",
                "page_no": 1,
                "item": {"object_type": "table"},
            },
            {
                "index": 1,
                "kind": "figure",
                "page_no": 2,
                "item": {"object_type": "image"},
            },
            {
                "index": 2,
                "kind": "figure",
                "page_no": 2,
                "item": {"object_type": "image"},
            },
        ],
        vision_results={
            0: {
                "index": 0,
                "kind": "table",
                "payload": {"rows": [["2025", "12"]]},
                "attempted": True,
                "elapsed_ms": 11,
                "serial_recovery_retry": True,
            },
            1: {
                "index": 1,
                "kind": "figure",
                "payload": {"summary": "chart"},
                "attempted": True,
                "elapsed_ms": 5,
            },
            2: {
                "index": 2,
                "kind": "figure",
                "payload": {"summary": "diagram"},
                "attempted": True,
                "elapsed_ms": 6,
            },
        },
        parts=[],
        bbox_map={},
        page_dims={1: (100.0, 100.0), 2: (100.0, 100.0)},
        runtime_table_max_per_page=1,
        runtime_figure_max_per_page=1,
        table_source="pdf_mineru_gemini",
        figure_source="pdf_mineru_gemini",
        vision_ready=True,
    )

    assert len(result["table_blocks"]) == 1
    assert len(result["figure_blocks"]) == 1
    assert result["figure_blocks"][0]["figure_id"] == "pdf_mineru_gemini_f1"
    assert result["vision_attempted_count"] == 3
    assert result["vision_success_count"] == 2
    assert result["vision_serial_recovery_retry_count"] == 1
    assert result["vision_serial_recovery_success_count"] == 1


def test_visual_result_materializer_runtime_marks_empty_attempts() -> None:
    runtime = VisualResultMaterializerRuntime(
        table_cell_cap=10,
        build_table_from_visual_payload=lambda **kwargs: (
            {
                "table_id": kwargs["table_id"],
                "page": kwargs["page_no"],
                "source": kwargs["source"],
            },
            kwargs["emitted_cells"] + 1,
        ),
        table_payload_has_content=lambda payload: False,
        build_figure_from_visual_payload=lambda **kwargs: None,
        figure_payload_has_content=lambda payload: False,
    )

    result = runtime.materialize(
        vision_jobs=[
            {
                "index": 0,
                "kind": "table",
                "page_no": 1,
                "item": {"object_type": "table"},
            }
        ],
        vision_results={
            0: {
                "index": 0,
                "kind": "table",
                "payload": {},
                "attempted": True,
                "elapsed_ms": 4,
            }
        },
        parts=[],
        bbox_map={},
        page_dims={1: (100.0, 100.0)},
        runtime_table_max_per_page=1,
        runtime_figure_max_per_page=1,
        table_source="pdf_mineru_gemini",
        figure_source="pdf_mineru_gemini",
        vision_ready=True,
    )

    assert len(result["table_blocks"]) == 1
    assert result["table_blocks"][0]["vision_status"] == "attempted_empty"
    assert result["vision_success_count"] == 0
    assert result["vision_empty_count"] == 1
