from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse

from app.core.config import Settings
from app.modules.frontend_static.service import serve_frontend_asset


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
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
    )


def test_serve_frontend_mjs_asset_uses_javascript_media_type(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    asset_path = settings.frontend_dist_dir / "assets" / "pdf.worker.min-test.mjs"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("export const ready = true;", encoding="utf-8")

    response = serve_frontend_asset(settings, "assets/pdf.worker.min-test.mjs")

    assert isinstance(response, FileResponse)
    assert response.media_type == "text/javascript"
