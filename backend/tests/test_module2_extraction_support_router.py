from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
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
    ["module2", "app", "api", "v1", "endpoints", "extraction_support.py"],
    "_smart_doc_flow_module2_api_v1_extraction_support_endpoint",
)

build_extraction_support_router = router_module.build_router


class _FakeOfficePreviewRuntime:
    def __init__(self) -> None:
        self.start_calls: list[dict[str, object]] = []
        self.status_calls: list[str] = []

    async def start(self, upload):
        payload = await upload.read()
        call = {"file_name": upload.filename, "file_size": len(payload)}
        self.start_calls.append(call)
        return {"job_id": "preview_job_1", **call}

    async def get_status(self, job_id: str):
        self.status_calls.append(job_id)
        return {"job_id": job_id, "status": "completed"}


class _FakeDocumentToolsRuntime:
    def __init__(self) -> None:
        self.summarize_calls: list[dict[str, object]] = []
        self.trace_calls: list[dict[str, object]] = []

    def summarize(self, payload):
        self.summarize_calls.append(dict(payload))
        return {"summary": "ok"}

    def trace_locate(self, payload):
        self.trace_calls.append(dict(payload))
        return {"hit_count": 0, "truncated": False, "hits": []}


def _build_app():
    office_preview_runtime = _FakeOfficePreviewRuntime()
    document_tools_runtime = _FakeDocumentToolsRuntime()
    clear_cache_calls: list[str] = []
    layout_calls: list[tuple[str, str]] = []
    artifact_calls: list[tuple[str, str]] = []
    health_calls: list[str] = []

    async def _clear_cache_request(scope: str):
        clear_cache_calls.append(scope)
        return {
            "ok": True,
            "message": "cache cleared",
            "scope": scope,
            "cache_counts": {},
            "removed_artifacts": 0,
            "removed_runtime_models": 0,
            "removed_materialized": {},
            "process_pool_reset_generation": 0,
        }

    def _serve_layout_preview(artifact_name: str, request_method: str):
        layout_calls.append((artifact_name, request_method))
        return PlainTextResponse("layout-preview")

    def _serve_artifact(artifact_path: str, request_method: str):
        artifact_calls.append((artifact_path, request_method))
        return PlainTextResponse("artifact-body")

    def _build_health_payload():
        health_calls.append("health")
        return {"status": "ok"}

    app = FastAPI()
    app.include_router(
        build_extraction_support_router(
            office_preview_request_runtime=office_preview_runtime,
            document_tools_runtime=document_tools_runtime,
            clear_cache_request=_clear_cache_request,
            serve_layout_preview=_serve_layout_preview,
            serve_artifact=_serve_artifact,
            build_health_payload=_build_health_payload,
        )
    )
    return (
        app,
        office_preview_runtime,
        document_tools_runtime,
        clear_cache_calls,
        layout_calls,
        artifact_calls,
        health_calls,
    )


def test_extraction_support_router_delegates_office_preview_routes() -> None:
    app, office_preview_runtime, _, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        start_response = client.post(
            "/extract/preview/office/start",
            files={"file": ("demo.docx", b"preview", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        status_response = client.get("/extract/preview/office/status/preview_job_1")

    assert start_response.status_code == 200
    assert start_response.json() == {
        "job_id": "preview_job_1",
        "file_name": "demo.docx",
        "file_size": 7,
    }
    assert status_response.status_code == 200
    assert status_response.json() == {"job_id": "preview_job_1", "status": "completed"}
    assert office_preview_runtime.start_calls == [{"file_name": "demo.docx", "file_size": 7}]
    assert office_preview_runtime.status_calls == ["preview_job_1"]


def test_extraction_support_router_delegates_tools_routes() -> None:
    app, _, document_tools_runtime, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        summarize_response = client.post("/extract/summarize", json={"file_name": "demo.pdf", "result": {}})
        trace_response = client.post("/extract/trace/locate", json={"document": {"file_name": "demo.pdf"}})

    assert summarize_response.status_code == 200
    assert summarize_response.json() == {"summary": "ok"}
    assert trace_response.status_code == 200
    assert trace_response.json() == {"hit_count": 0, "truncated": False, "hits": []}
    assert document_tools_runtime.summarize_calls == [{"file_name": "demo.pdf", "result": {}}]
    assert document_tools_runtime.trace_calls == [{"document": {"file_name": "demo.pdf"}}]


def test_extraction_support_router_delegates_cache_and_health_routes() -> None:
    app, _, _, clear_cache_calls, _, _, health_calls = _build_app()

    with TestClient(app) as client:
        cache_response = client.post("/extract/cache/clear?scope=all")
        health_response = client.get("/healthz")

    assert cache_response.status_code == 200
    assert cache_response.json()["scope"] == "all"
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert clear_cache_calls == ["all"]
    assert health_calls == ["health"]


def test_extraction_support_router_delegates_artifact_routes() -> None:
    app, _, _, _, layout_calls, artifact_calls, _ = _build_app()

    with TestClient(app) as client:
        layout_response = client.get("/extract/layout-preview/preview.html")
        artifact_response = client.head("/extract/artifact/reports/demo.txt")

    assert layout_response.status_code == 200
    assert layout_response.text == "layout-preview"
    assert artifact_response.status_code == 200
    assert artifact_response.text == ""
    assert layout_calls == [("preview.html", "GET")]
    assert artifact_calls == [("reports/demo.txt", "HEAD")]
