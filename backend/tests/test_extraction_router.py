from __future__ import annotations

from pathlib import Path

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_settings
from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.factory import create_app
from app.modules.module2.services.api.extraction_service import get_extraction_service


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user-123",
        name="Tester",
        email="tester@example.com",
        phone="13900000000",
        status="active",
        session_id="sess-123",
    )


def _build_app(settings: Settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_authenticated_user] = _fake_user
    return app


class FakeExtractionService:
    def __init__(self) -> None:
        self.batch_calls: list[dict[str, object]] = []
        self.cache_calls: list[str] = []
        self.preview_start_calls: list[dict[str, object]] = []
        self.preview_status_calls: list[str] = []
        self.assistant_calls: list[dict[str, object]] = []

    async def extract_batch(self, settings, request, uploads, schema_form: str, tenant_id: str = "") -> dict:
        file_names = [upload.filename for upload in uploads]
        file_sizes = [len(await upload.read()) for upload in uploads]
        self.batch_calls.append(
            {
                "settings_port": settings.gateway_port,
                "path": str(request.url.path),
                "tenant_id": tenant_id,
                "schema_form": schema_form,
                "file_names": file_names,
                "file_sizes": file_sizes,
                "trace_header": request.headers.get("x-tenant-trace"),
            }
        )
        return {
            "documents": [
                {
                    "file_name": file_names[0],
                    "file_hash": "hash-demo-1",
                    "track": "done",
                    "cached": False,
                    "result": {
                        "contract_amount": {
                            "value": "100",
                            "confidence": 0.93,
                            "source_ref_id": "ref-1",
                            "bbox": [1, 10, 20, 30, 40],
                        }
                    },
                    "errors": [],
                    "soft_warnings": [],
                    "trace_hits": [],
                    "trace_stats": {},
                    "diagnostics": {},
                }
            ]
        }

    async def clear_cache(self, settings, scope: str = "results") -> dict:
        del settings
        self.cache_calls.append(scope)
        return {
            "ok": True,
            "message": "cache cleared",
            "scope": scope,
            "cache_counts": {
                "unified_shadow_jobs_memory": 3,
                "unified_shadow_pollers_memory": 1,
                "unified_office_preview_jobs_memory": 2,
            },
            "removed_artifacts": 0,
            "removed_runtime_models": 0,
            "removed_materialized": {"removed_shadow_snapshots": 4},
            "process_pool_reset_generation": 0,
        }

    async def start_office_preview(self, settings, request, upload) -> dict:
        del settings, request
        file_bytes = await upload.read()
        payload = {
            "job_id": "preview_job_1",
            "status": "queued",
            "file_name": upload.filename,
            "file_size": len(file_bytes),
            "artifact_url": None,
        }
        self.preview_start_calls.append(payload)
        return payload

    async def get_office_preview_status(self, settings, request, job_id: str) -> dict:
        del settings, request
        self.preview_status_calls.append(job_id)
        return {
            "job_id": job_id,
            "status": "completed",
            "file_name": "demo.docx",
            "artifact_url": "/extract/artifact/preview/op/demo.pdf",
        }

    def build_assistant1_stream(self, settings, request, payload) -> StreamingResponse:
        self.assistant_calls.append(
            {
                "gateway_port": settings.gateway_port,
                "path": str(request.url.path),
                "message": payload.message,
                "file_hash": payload.file_hash,
                "supports_replace": payload.client_caps.supports_replace,
            }
        )
        return StreamingResponse(
            iter([b"event: assistant.done\ndata: {\"final_text\":\"ok\"}\n\n"]),
            media_type="text/event-stream",
        )


def test_extract_batch_endpoint_accepts_form_and_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)
    fake_service = FakeExtractionService()
    app.dependency_overrides[get_extraction_service] = lambda: fake_service

    with TestClient(app) as client:
        response = client.post(
            "/extract/batch",
            data={"schema": '{"fields":["contract_amount"]}', "tenant_id": "tenant-a"},
            files=[
                ("files", ("demo.pdf", b"%PDF-1.4 sample", "application/pdf")),
                ("files", ("notes.txt", b"hello", "text/plain")),
            ],
            headers={"X-Tenant-Trace": "trace-001"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["file_name"] == "demo.pdf"
    assert fake_service.batch_calls == [
        {
            "settings_port": 3001,
            "path": "/extract/batch",
            "tenant_id": "tenant-a",
            "schema_form": '{"fields":["contract_amount"]}',
            "file_names": ["demo.pdf", "notes.txt"],
            "file_sizes": [15, 5],
            "trace_header": "trace-001",
        }
    ]


def test_extract_cache_clear_endpoint_returns_unified_payload(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)
    fake_service = FakeExtractionService()
    app.dependency_overrides[get_extraction_service] = lambda: fake_service

    with TestClient(app) as client:
        response = client.post("/extract/cache/clear?scope=all")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["scope"] == "all"
    assert payload["cache_counts"]["unified_shadow_jobs_memory"] == 3
    assert payload["removed_materialized"]["removed_shadow_snapshots"] == 4
    assert fake_service.cache_calls == ["all"]


def test_extract_office_preview_routes_delegate_to_service(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)
    fake_service = FakeExtractionService()
    app.dependency_overrides[get_extraction_service] = lambda: fake_service

    with TestClient(app) as client:
        start_response = client.post(
            "/extract/preview/office/start",
            files={
                "file": (
                    "demo.docx",
                    b"preview-content",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        status_response = client.get("/extract/preview/office/status/preview_job_1")

    app.dependency_overrides.clear()

    assert start_response.status_code == 200
    assert start_response.json()["job_id"] == "preview_job_1"
    assert start_response.json()["file_name"] == "demo.docx"
    assert start_response.json()["file_size"] == 15
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert fake_service.preview_status_calls == ["preview_job_1"]


def test_extract_artifact_legacy_path_route_is_rejected(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("AUTH_TENANT_MODE", "compat_default")
    monkeypatch.setenv("AUTH_TENANT_DEFAULT_ID", "")
    monkeypatch.setenv("UNIFIED_EXTRACT_ARTIFACT_TENANT_GUARD_MODE", "compat")
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(settings.data_root_dir / "module2" / "artifacts"))
    artifact_path = settings.data_root_dir / "module2" / "artifacts" / "reports" / "demo.txt"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("hello artifact", encoding="utf-8")

    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/extract/artifact/reports/demo.txt")

    app.dependency_overrides.clear()

    assert response.status_code == 410
    assert "legacy artifact path route is disabled" in str(response.json().get("detail") or "")


def test_extract_layout_preview_legacy_path_route_is_rejected(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("AUTH_TENANT_MODE", "compat_default")
    monkeypatch.setenv("AUTH_TENANT_DEFAULT_ID", "")
    monkeypatch.setenv("UNIFIED_EXTRACT_ARTIFACT_TENANT_GUARD_MODE", "compat")
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(settings.data_root_dir / "module2" / "artifacts"))
    preview_path = settings.data_root_dir / "module2" / "artifacts" / "layout" / "preview.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_content = "<html><body>preview</body></html>"
    preview_path.write_text(preview_content, encoding="utf-8")

    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.head("/extract/layout-preview/preview.html")

    app.dependency_overrides.clear()

    assert response.status_code == 410


def test_extract_artifact_by_file_id_endpoint_serves_file_asset(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    artifact_file = (tmp_path / "runtime-data" / "file-assets" / "demo.txt").resolve()
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text("hello by file id", encoding="utf-8")

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.resolve_file_for_owner",
        lambda file_id, owner_id: (
            {
                "file_id": file_id,
                "filename": "demo.txt",
                "mime_type": "text/plain",
            },
            artifact_file,
        ),
    )

    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/extract/artifact/by-file/fa_demo")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "hello by file id"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert response.headers.get("X-Extract-Legacy-Route-Mode") == "off"


def test_extract_artifact_route_prefers_file_id_query_when_present(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    artifact_file = (tmp_path / "runtime-data" / "file-assets" / "prefer.txt").resolve()
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text("prefer file id", encoding="utf-8")

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.resolve_file_for_owner",
        lambda file_id, owner_id: (
            {
                "file_id": file_id,
                "filename": "prefer.txt",
                "mime_type": "text/plain",
            },
            artifact_file,
        ),
    )

    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/extract/artifact/path/that/does/not/exist.txt?file_id=fa_prefer")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "prefer file id"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers.get("Deprecation") is None
    assert response.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert response.headers.get("X-Extract-Legacy-Route-Mode") == "off"


def test_extract_layout_preview_by_file_id_head_returns_file_metadata(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    preview_file = (tmp_path / "runtime-data" / "file-assets" / "preview.html").resolve()
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_content = "<html><body>preview by file id</body></html>"
    preview_file.write_text(preview_content, encoding="utf-8")

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.resolve_file_for_owner",
        lambda file_id, owner_id: (
            {
                "file_id": file_id,
                "filename": "preview.html",
                "mime_type": "text/html",
            },
            preview_file,
        ),
    )

    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.head("/extract/layout-preview/by-file/fa_preview")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["content-length"] == str(len(preview_content.encode("utf-8")))
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers.get("X-Extract-Resolved-Via") == "by-file"
    assert response.headers.get("X-Extract-Legacy-Route-Mode") == "off"


def test_extract_artifact_legacy_path_mode_compat_still_rejects_legacy_route(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("UNIFIED_EXTRACT_LEGACY_ARTIFACT_ROUTE_MODE", "compat")
    monkeypatch.setenv("AUTH_TENANT_MODE", "compat_default")
    monkeypatch.setenv("AUTH_TENANT_DEFAULT_ID", "")
    monkeypatch.setenv("UNIFIED_EXTRACT_ARTIFACT_TENANT_GUARD_MODE", "compat")
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(settings.data_root_dir / "module2" / "artifacts"))

    artifact_path = settings.data_root_dir / "module2" / "artifacts" / "reports" / "demo-compat.txt"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("compat mode", encoding="utf-8")

    app = _build_app(settings)
    with TestClient(app) as client:
        response = client.get("/extract/artifact/reports/demo-compat.txt")
    app.dependency_overrides.clear()

    assert response.status_code == 410
    assert "legacy artifact path route is disabled" in str(response.json().get("detail") or "")


def test_extract_artifact_legacy_path_mode_off_rejects_legacy_route(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setenv("UNIFIED_EXTRACT_LEGACY_ARTIFACT_ROUTE_MODE", "off")
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/extract/artifact/reports/demo-off.txt")

    app.dependency_overrides.clear()

    assert response.status_code == 410
    assert "legacy artifact path route is disabled" in str(response.json().get("detail") or "")


def test_extract_assistant1_stream_endpoint_passes_settings_and_payload(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)
    fake_service = FakeExtractionService()
    app.dependency_overrides[get_extraction_service] = lambda: fake_service

    with TestClient(app) as client:
        response = client.post(
            "/extract/assistant1/chat/stream",
            json={
                "message": "请总结这个文件",
                "file_hash": "hash-demo-1",
                "client_caps": {"supports_replace": True},
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "assistant.done" in response.text
    assert fake_service.assistant_calls == [
        {
            "gateway_port": 3001,
            "path": "/extract/assistant1/chat/stream",
            "message": "请总结这个文件",
            "file_hash": "hash-demo-1",
            "supports_replace": True,
        }
    ]
