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
    ["app", "modules", "module2", "api", "v1", "endpoints", "extraction_support.py"],
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
        self.summarize_calls.append(payload.model_dump(exclude_unset=True))
        return {"summary": "ok"}

    def trace_locate(self, payload):
        self.trace_calls.append(payload.model_dump(exclude_unset=True))
        return {"hit_count": 0, "truncated": False, "hits": []}


def _build_app():
    office_preview_runtime = _FakeOfficePreviewRuntime()
    document_tools_runtime = _FakeDocumentToolsRuntime()
    clear_cache_calls: list[str] = []
    layout_calls: list[tuple[str, str]] = []
    artifact_calls: list[tuple[str, str]] = []
    file_asset_calls: list[tuple[str, str]] = []
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

    def _serve_file_asset(file_id: str, request_method: str):
        file_asset_calls.append((file_id, request_method))
        return PlainTextResponse(f"file-asset:{file_id}")

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
            serve_file_asset=_serve_file_asset,
        )
    )
    return (
        app,
        office_preview_runtime,
        document_tools_runtime,
        clear_cache_calls,
        layout_calls,
        artifact_calls,
        file_asset_calls,
        health_calls,
    )


def test_extraction_support_router_delegates_office_preview_routes() -> None:
    app, office_preview_runtime, _, _, _, _, _, _ = _build_app()

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
    app, _, document_tools_runtime, _, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        summarize_response = client.post("/extract/summarize", json={"file_name": "demo.pdf", "result": {}})
        trace_response = client.post("/extract/trace/locate", json={"document": {"file_name": "demo.pdf", "file_hash": "hash-demo", "result": {}}})

    assert summarize_response.status_code == 200
    assert summarize_response.json() == {"summary": "ok"}
    assert trace_response.status_code == 200
    assert trace_response.json() == {"hit_count": 0, "truncated": False, "hits": []}
    assert document_tools_runtime.summarize_calls == [{"file_name": "demo.pdf", "result": {}}]
    assert document_tools_runtime.trace_calls == [{"document": {"file_name": "demo.pdf", "file_hash": "hash-demo", "result": {}}}]


def test_extraction_support_router_delegates_cache_and_health_routes() -> None:
    app, _, _, clear_cache_calls, _, _, _, health_calls = _build_app()

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
    app, _, _, _, layout_calls, artifact_calls, _, _ = _build_app()

    with TestClient(app) as client:
        layout_response = client.get("/extract/layout-preview/preview.html")
        artifact_response = client.head("/extract/artifact/reports/demo.txt")

    assert layout_response.status_code == 410
    assert artifact_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(layout_response.json().get("detail") or "")
    assert layout_calls == []
    assert artifact_calls == []


def test_extraction_support_router_prefers_file_id_routes_when_available() -> None:
    app, _, _, _, layout_calls, artifact_calls, file_asset_calls, _ = _build_app()

    with TestClient(app) as client:
        direct_by_file = client.get("/extract/artifact/by-file/fa_direct")
        query_by_file = client.get("/extract/artifact/reports/demo.txt?file_id=fa_query")
        layout_by_file = client.head("/extract/layout-preview/preview.html?file_id=fa_layout")

    assert direct_by_file.status_code == 200
    assert direct_by_file.text == "file-asset:fa_direct"
    assert query_by_file.status_code == 200
    assert query_by_file.text == "file-asset:fa_query"
    assert layout_by_file.status_code == 200
    assert layout_by_file.text == ""
    assert direct_by_file.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert query_by_file.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert layout_by_file.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert direct_by_file.headers.get("X-Extract-Legacy-Route-Mode") == "off"
    assert layout_calls == []
    assert artifact_calls == []
    assert file_asset_calls == [
        ("fa_direct", "GET"),
        ("fa_query", "GET"),
        ("fa_layout", "HEAD"),
    ]


def test_extraction_support_router_path_routes_always_rejected() -> None:
    app, _, _, _, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        artifact_response = client.get("/extract/artifact/reports/demo.txt")
        layout_response = client.get("/extract/layout-preview/preview.html")

    assert artifact_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(artifact_response.json().get("detail") or "")
    assert layout_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(layout_response.json().get("detail") or "")


def test_extraction_support_router_legacy_path_mode_compat_still_rejects_path_route(monkeypatch) -> None:
    monkeypatch.setenv("UNIFIED_EXTRACT_LEGACY_ARTIFACT_ROUTE_MODE", "compat")
    app, _, _, _, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        artifact_response = client.get("/extract/artifact/reports/demo.txt")
        layout_response = client.get("/extract/layout-preview/preview.html")

    assert artifact_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(artifact_response.json().get("detail") or "")
    assert layout_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(layout_response.json().get("detail") or "")


def test_extraction_support_router_legacy_path_mode_off_rejects_path_route(monkeypatch) -> None:
    monkeypatch.setenv("UNIFIED_EXTRACT_LEGACY_ARTIFACT_ROUTE_MODE", "off")
    app, _, _, _, _, _, _, _ = _build_app()

    with TestClient(app) as client:
        artifact_response = client.get("/extract/artifact/reports/demo.txt")
        layout_response = client.get("/extract/layout-preview/preview.html")
        by_file_response = client.get("/extract/artifact/by-file/fa_still_ok")

    assert artifact_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(artifact_response.json().get("detail") or "")
    assert layout_response.status_code == 410
    assert "legacy artifact path route is disabled" in str(layout_response.json().get("detail") or "")
    assert by_file_response.status_code == 200
    assert by_file_response.text == "file-asset:fa_still_ok"
    assert by_file_response.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert by_file_response.headers.get("X-Extract-Legacy-Route-Mode") == "off"


def test_extraction_support_router_passes_request_to_request_aware_file_asset_handler() -> None:
    captured: list[dict[str, str]] = []

    async def _clear_cache_request(scope: str):
        del scope
        return {
            "ok": True,
            "message": "cache cleared",
            "scope": "results",
            "cache_counts": {},
            "removed_artifacts": 0,
            "removed_runtime_models": 0,
            "removed_materialized": {},
            "process_pool_reset_generation": 0,
        }

    def _serve_file_asset(file_id: str, request_method: str, *, request=None):
        captured.append(
            {
                "file_id": file_id,
                "request_method": request_method,
                "path": str(getattr(getattr(request, "url", None), "path", "")),
            }
        )
        return PlainTextResponse(f"request-aware:{file_id}")

    app = FastAPI()
    app.include_router(
        build_extraction_support_router(
            office_preview_request_runtime=_FakeOfficePreviewRuntime(),
            document_tools_runtime=_FakeDocumentToolsRuntime(),
            clear_cache_request=_clear_cache_request,
            serve_layout_preview=lambda *_args, **_kwargs: PlainTextResponse("layout"),
            serve_artifact=lambda *_args, **_kwargs: PlainTextResponse("artifact"),
            build_health_payload=lambda: {"status": "ok"},
            serve_file_asset=_serve_file_asset,
        )
    )

    with TestClient(app) as client:
        response = client.get("/extract/artifact/by-file/fa_req")

    assert response.status_code == 200
    assert response.text == "request-aware:fa_req"
    assert response.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert response.headers.get("X-Extract-Legacy-Route-Mode") == "off"
    assert captured == [
        {
            "file_id": "fa_req",
            "request_method": "GET",
            "path": "/extract/artifact/by-file/fa_req",
        }
    ]
