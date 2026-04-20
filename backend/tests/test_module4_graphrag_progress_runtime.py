from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


runtime_module = import_module("app.modules.module4.services.ingestion.runtime")


def _write_progress_logs(workspace_dir: Path) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    primary_log_path = workspace_dir / "graphrag-index.log"
    primary_log_path.write_text(
        "\n".join(
            [
                "Starting workflow: load_input_documents",
                "",
                "Workflow complete: load_input_documents",
                "Starting workflow: create_base_text_units",
                "  1 / 1 ........................................................",
                "Workflow complete: create_base_text_units",
                "Starting workflow: create_final_documents",
                "Workflow complete: create_final_documents",
                "Starting workflow: extract_graph",
                "  1 / 12 ",
            ]
        ),
        encoding="utf-8",
    )

    report_dir = workspace_dir / "output" / "20260420-013112" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "indexing-engine.log").write_text(
        "\n".join(
            [
                "2026-04-20 09:32:09.0814 - INFO - graphrag.index.workflows.extract_graph - Workflow started: extract_graph",
                "2026-04-20 09:35:26.0284 - INFO - graphrag.logger.progress - extract graph progress: 2/12",
                "2026-04-20 09:35:49.0997 - INFO - graphrag.logger.progress - extract graph progress: 3/12",
            ]
        ),
        encoding="utf-8",
    )
    return primary_log_path


def test_inspect_graphrag_progress_snapshot_reads_wrapper_and_engine_logs(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    primary_log_path = _write_progress_logs(workspace_dir)

    progress, details = runtime_module._inspect_graphrag_progress_snapshot(
        primary_log_path=primary_log_path,
        workspace_dir=workspace_dir,
    )

    assert progress is not None
    assert progress > 31.0
    assert isinstance(details, dict)
    assert details["graphrag_workflow"] == "extract_graph"
    assert details["graphrag_workflow_progress"] == 25.0
    assert str(details["graphrag_log_path"]).endswith("indexing-engine.log")


class _FakeStorage:
    def __init__(self, row: Dict[str, Any]) -> None:
        self.row = dict(row)
        self.update_calls: list[Dict[str, Any]] = []

    async def update_job(self, job_id: str, **fields: Any) -> Dict[str, Any]:
        assert job_id == str(self.row.get("job_id"))
        self.update_calls.append(dict(fields))
        self.row.update(fields)
        return dict(self.row)


async def _refresh_with_storage(storage: _FakeStorage, row: Dict[str, Any]) -> Dict[str, Any]:
    return await runtime_module.refresh_running_job_progress_from_logs(
        storage=storage,
        row=row,
    )


def test_refresh_running_job_progress_from_logs_persists_new_progress(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    primary_log_path = _write_progress_logs(workspace_dir)
    row = {
        "job_id": "job-1",
        "status": "running",
        "progress": 18.0,
        "result": {
            "stage": "indexing_graph",
            "workspace_dir": str(workspace_dir),
            "graphrag_log_path": str(primary_log_path),
        },
    }
    storage = _FakeStorage(row)

    import asyncio

    updated = asyncio.run(_refresh_with_storage(storage, row))

    assert len(storage.update_calls) == 1
    assert float(updated["progress"]) > 18.0
    assert updated["result"]["graphrag_workflow"] == "extract_graph"
    assert updated["result"]["graphrag_workflow_progress"] == 25.0
