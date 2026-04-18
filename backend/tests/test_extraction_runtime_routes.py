from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_settings
from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.factory import create_app


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


def _build_app(settings: Settings):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
        user_id="test-user",
        name="Test User",
        email="test@example.com",
        phone="",
        status="active",
        session_id="session-test",
    )
    return app


def test_extract_summarize_endpoint_uses_real_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/extract/summarize",
            json={
                "file_name": "demo.pdf",
                "result": {
                    "contract_amount": {
                        "value": "1000",
                        "confidence": 0.95,
                    }
                },
                "trace_hits": [],
                "diagnostics": {},
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]
    assert "demo.pdf" in payload["summary"]
    assert "1000" in payload["summary"]


def test_extract_trace_locate_endpoint_uses_real_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/extract/trace/locate",
            json={
                "document": {
                    "file_name": "demo.pdf",
                    "file_hash": "hash-demo-2",
                    "track": "done",
                    "cached": False,
                    "result": {
                        "contract_amount": {
                            "value": "2000",
                            "confidence": 0.91,
                            "source_ref_id": "ref-1",
                            "bbox": [3, 11, 21, 31, 41],
                        }
                    },
                    "errors": [],
                    "soft_warnings": [],
                    "trace_hits": [],
                    "trace_stats": {},
                    "diagnostics": {},
                },
                "field_name": "contract_amount",
                "file_name": "demo.pdf",
                "object_type": "field",
                "top_k": 5,
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["hit_count"] == 1
    assert payload["truncated"] is False
    assert payload["hits"][0]["object_id"] == "contract_amount"
    assert payload["hits"][0]["ref_id"] == "ref-1"
    assert payload["hits"][0]["page"] == 3
