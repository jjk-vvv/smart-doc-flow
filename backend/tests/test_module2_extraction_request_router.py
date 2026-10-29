from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


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


router_module = _load_module(
    ["app", "modules", "module2", "api", "v1", "endpoints", "extraction_request.py"],
    "_smart_doc_flow_module2_api_v1_extraction_request_endpoint",
)

build_extraction_request_router = router_module.build_router


class _FakeExtractionRequestRuntime:
    def __init__(self) -> None:
        self.create_job_calls: list[dict[str, object]] = []
        self.get_job_status_calls: list[dict[str, object]] = []
        self.graph_sync_calls: list[dict[str, object]] = []
        self.extract_batch_calls: list[dict[str, object]] = []

    async def create_job(self, *, request, files, schema_form: str, tenant_id: str = "") -> dict:
        self.create_job_calls.append(
            {
                "path": str(request.url.path),
                "tenant_id": tenant_id,
                "schema_form": schema_form,
                "file_names": [upload.filename for upload in files],
            }
        )
        return {"job_id": "extract_job_1", "status": "queued"}

    async def get_job_status(self, job_id: str, *, include_documents: bool = False) -> dict:
        self.get_job_status_calls.append(
            {
                "job_id": job_id,
                "include_documents": include_documents,
            }
        )
        return {"job_id": job_id, "status": "completed", "include_documents": include_documents}

    async def extract_batch(self, *, request, files, schema_form: str, tenant_id: str = ""):
        payload = {
            "path": str(request.url.path),
            "tenant_id": tenant_id,
            "schema_form": schema_form,
            "file_names": [upload.filename for upload in files],
        }
        self.extract_batch_calls.append(payload)
        return {
            "documents": [
                {
                    "file_name": "demo.pdf",
                    "file_hash": "hash-demo",
                    "track": "VisualTrack",
                    "cached": False,
                    "result": {},
                    "errors": [],
                    "soft_warnings": [],
                    "trace_hits": [],
                    "trace_stats": {},
                    "diagnostics": {},
                }
            ]
        }

    async def trigger_graph_sync(
        self,
        *,
        request,
        payload: dict[str, object] | None = None,
        background_tasks=None,
    ) -> dict[str, object]:
        normalized_payload = dict(payload or {})
        call = {
            "path": str(request.url.path),
            "payload": normalized_payload,
            "has_background_tasks": background_tasks is not None,
        }
        self.graph_sync_calls.append(call)
        return {
            "ok": True,
            "enqueued": True,
            "file_name": str(normalized_payload.get("file_name") or ""),
            "file_hash": str(normalized_payload.get("file_hash") or ""),
        }


def _build_app(runtime: _FakeExtractionRequestRuntime) -> FastAPI:
    app = FastAPI()
    app.include_router(build_extraction_request_router(extraction_request_runtime=runtime))
    return app


def test_extraction_request_router_delegates_jobs_create() -> None:
    runtime = _FakeExtractionRequestRuntime()
    app = _build_app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/extract/jobs/create",
            data={"schema": '{"fields":["amount"]}', "tenant_id": "tenant-a"},
            files=[("files", ("demo.pdf", b"%PDF", "application/pdf"))],
        )

    assert response.status_code == 200
    assert response.json() == {"job_id": "extract_job_1", "status": "queued"}
    assert runtime.create_job_calls == [
        {
            "path": "/extract/jobs/create",
            "tenant_id": "tenant-a",
            "schema_form": '{"fields":["amount"]}',
            "file_names": ["demo.pdf"],
        }
    ]


def test_extraction_request_router_delegates_jobs_status() -> None:
    runtime = _FakeExtractionRequestRuntime()
    app = _build_app(runtime)

    with TestClient(app) as client:
        response = client.get("/extract/jobs/status/extract_job_1?include_documents=true")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "extract_job_1",
        "status": "completed",
        "include_documents": True,
    }
    assert runtime.get_job_status_calls == [
        {
            "job_id": "extract_job_1",
            "include_documents": True,
        }
    ]


def test_extraction_request_router_delegates_graph_sync() -> None:
    runtime = _FakeExtractionRequestRuntime()
    app = _build_app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/extract/graph-sync",
            json={
                "job_id": "extract_job_1",
                "file_name": "demo.pdf",
                "file_hash": "hash-demo",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "enqueued": True,
        "file_name": "demo.pdf",
        "file_hash": "hash-demo",
    }
    assert runtime.graph_sync_calls == [
        {
            "path": "/extract/graph-sync",
            "payload": {
                "job_id": "extract_job_1",
                "file_name": "demo.pdf",
                "file_hash": "hash-demo",
            },
            "has_background_tasks": True,
        }
    ]


def test_extraction_request_router_delegates_batch_extract() -> None:
    runtime = _FakeExtractionRequestRuntime()
    app = _build_app(runtime)

    with TestClient(app) as client:
        response = client.post(
            "/extract/batch",
            data={"schema": '{"fields":["amount"]}', "tenant_id": "tenant-a"},
            files=[("files", ("demo.pdf", b"%PDF", "application/pdf"))],
        )

    assert response.status_code == 200
    assert response.json()["documents"][0]["file_name"] == "demo.pdf"
    assert runtime.extract_batch_calls == [
        {
            "path": "/extract/batch",
            "tenant_id": "tenant-a",
            "schema_form": '{"fields":["amount"]}',
            "file_names": ["demo.pdf"],
        }
    ]
