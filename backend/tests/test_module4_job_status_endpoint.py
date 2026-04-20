from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


endpoint_module = import_module("app.modules.module4.api.v1.endpoints.module4")
deps_module = import_module("app.modules.module4.api.deps")


class _FakeStorage:
    def __init__(self, row: Dict[str, Any]) -> None:
        self._row = dict(row)

    async def get_job(self, job_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if job_id != str(self._row.get("job_id")):
            return None
        if tenant_id and tenant_id != str(self._row.get("tenant_id")):
            return None
        return dict(self._row)


def _build_app(row: Dict[str, Any]) -> FastAPI:
    deps = deps_module.Module4RouterDeps(
        storage_getter=lambda: _FakeStorage(row),
        query_helpers=object(),
        insight_helpers=object(),
        workspace_builder_getter=lambda: object(),
        neo4j_graph_projector_getter=lambda: object(),
        graphrag_indexer_getter=lambda: object(),
        tenant_from_request=lambda _request, candidate=None: str(candidate or "tenant-a"),
        validate_internal_request=lambda _request=None: None,
        parse_csv_list=lambda value: [item.strip() for item in str(value or "").split(",") if item.strip()],
        submit_ingest_job=lambda *_args, **_kwargs: None,
        schedule_rebuild_job=lambda *_args, **_kwargs: None,
        now_utc=lambda: None,
    )
    app = FastAPI()
    app.include_router(endpoint_module.build_router(deps=deps))
    return app


def test_module4_job_status_default_returns_full_payload_and_result() -> None:
    app = _build_app(
        {
            "job_id": "job-1",
            "tenant_id": "tenant-a",
            "job_type": "ingest",
            "status": "running",
            "progress": 62.5,
            "error_message": None,
            "payload": {
                "source": "module2",
                "documents": [{"file_name": "demo.docx"}],
            },
            "result": {
                "stage": "indexing_graph",
                "nodes": 128,
                "edges": 256,
                "import_summary": {"alerts": 3},
            },
            "created_at": None,
            "started_at": None,
            "finished_at": None,
        }
    )
    client = TestClient(app)

    response = client.get("/module4/jobs/job-1?tenant_id=tenant-a")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["payload"]["source"] == "module2"
    assert payload["result"]["stage"] == "indexing_graph"
    assert payload["result"]["nodes"] == 128
    assert payload["result"]["import_summary"] == {"alerts": 3}


def test_module4_job_status_status_only_trims_payload_and_result() -> None:
    app = _build_app(
        {
            "job_id": "job-1",
            "tenant_id": "tenant-a",
            "job_type": "ingest",
            "status": "failed",
            "progress": 78.0,
            "error_message": "graph import failed",
            "payload": {
                "source": "module2",
                "documents": [{"file_name": "demo.docx"}],
            },
            "result": {
                "stage": "failed",
                "failure_stage": "importing_graph",
                "failure_category": "artifact_quality_failed",
                "nodes": 128,
                "edges": 256,
                "workspace_dir": "D:/tmp/ws-1",
                "import_summary": {"alerts": 3},
            },
            "created_at": None,
            "started_at": None,
            "finished_at": None,
        }
    )
    client = TestClient(app)

    response = client.get("/module4/jobs/job-1?tenant_id=tenant-a&status_only=true")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["progress"] == 78.0
    assert payload["payload"] == {}
    assert payload["result"] == {
        "stage": "failed",
        "failure_stage": "importing_graph",
        "failure_category": "artifact_quality_failed",
    }
