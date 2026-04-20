from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings
from app.core.deps import get_settings
from app.modules.module2.api.endpoints.extraction import build_router
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


class _FakeExtractionService:
    def __init__(self) -> None:
        self.status_calls: list[dict[str, object]] = []

    def get_job_status(
        self,
        settings,
        request,
        job_id: str,
        *,
        include_documents: bool = False,
        status_only: bool = False,
    ) -> dict[str, object]:
        self.status_calls.append(
            {
                "settings_port": settings.gateway_port,
                "path": str(request.url.path),
                "job_id": job_id,
                "include_documents": include_documents,
                "status_only": status_only,
            }
        )
        return {
            "job_id": job_id,
            "status": "completed",
            "include_documents": include_documents,
            "status_only": status_only,
        }


def _build_app(settings: Settings, service: _FakeExtractionService) -> FastAPI:
    app = FastAPI()
    app.include_router(build_router())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_extraction_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = _fake_user
    return app


def test_extract_jobs_status_endpoint_runs_sync_service_off_event_loop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = _FakeExtractionService()
    app = _build_app(settings, service)

    with TestClient(app) as client:
        response = client.get("/extract/jobs/status/extractjobdemo123?include_documents=true&status_only=true")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "extractjobdemo123",
        "status": "completed",
        "include_documents": True,
        "status_only": True,
    }
    assert service.status_calls == [
        {
            "settings_port": 3001,
            "path": "/extract/jobs/status/extractjobdemo123",
            "job_id": "extractjobdemo123",
            "include_documents": True,
            "status_only": True,
        }
    ]
