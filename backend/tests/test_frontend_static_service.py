from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.core.deps import get_settings
from app.modules.frontend_static.api.endpoints.frontend_static import router as frontend_static_router
from app.services.frontend_static_service import serve_frontend_app_asset, serve_frontend_asset


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_app_dist_dir = tmp_path / "frontend-app" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    frontend_app_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend_app_dist_dir / "index.html").write_text("<html>mobile</html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=5.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
        frontend_app_dist_dir=frontend_app_dist_dir,
    )


def test_serve_frontend_mjs_asset_uses_javascript_media_type(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    asset_path = settings.frontend_dist_dir / "assets" / "pdf.worker.min-test.mjs"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("export const ready = true;", encoding="utf-8")

    response = serve_frontend_asset(settings, "assets/pdf.worker.min-test.mjs")

    assert isinstance(response, FileResponse)
    assert response.media_type == "text/javascript"


def test_serve_mobile_frontend_asset_reads_from_mobile_dist(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    asset_path = settings.frontend_app_dist_dir / "assets" / "mobile-entry.js"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("console.log('mobile');", encoding="utf-8")

    response = serve_frontend_app_asset(settings, "assets/mobile-entry.js")

    assert isinstance(response, FileResponse)
    assert str(response.path).endswith("frontend-app\\dist\\assets\\mobile-entry.js")


def test_frontend_root_redirects_mobile_user_agents_to_mobile_entry(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    app.include_router(frontend_static_router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.get(
            "/",
            headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Mobile"},
            follow_redirects=False,
        )

    app.dependency_overrides.clear()

    assert response.status_code == 307
    assert response.headers["location"].endswith("/m/")


def test_frontend_root_respects_desktop_view_override(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    app.include_router(frontend_static_router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.get(
            "/?view=desktop",
            headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Mobile"},
            follow_redirects=False,
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200


def test_mobile_frontend_path_serves_mobile_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    app.include_router(frontend_static_router)
    app.dependency_overrides[get_settings] = lambda: settings

    with TestClient(app) as client:
        response = client.get("/m/")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "mobile" in response.text
