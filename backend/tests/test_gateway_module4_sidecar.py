from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_settings
from app.modules.module4.api.endpoints.gateway import router as gateway_router
from app.services.gateway_service import (
    build_gateway_health,
    build_gateway_info,
    proxy_module4_request,
)


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
        module2_upstream_url="http://127.0.0.1:3001",
        module4_upstream_url="http://127.0.0.1:3001",
    )


async def _empty_body() -> bytes:
    return b""


def test_gateway_info_reports_module4_as_local_target(tmp_path: Path) -> None:
    payload = build_gateway_info(_settings(tmp_path))

    assert payload["ok"] is True
    assert payload["gateway"]["port"] == 3001
    assert payload["upstreams"]["module4"]["mode"] == "local"
    assert payload["upstreams"]["module4"]["sidecar"] is None


def test_gateway_health_includes_local_module4_payload(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class _FakeAuthService:
        async def health_payload(self) -> dict[str, object]:
            return {"ok": True, "service": "auth"}

    async def _fake_module4_health_payload(probe: str = "basic") -> dict[str, object]:
        assert probe == "basic"
        return {"ok": True, "status": "ok", "service": "module4"}

    monkeypatch.setattr(
        "app.services.gateway_service.get_auth_service",
        lambda: _FakeAuthService(),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_service",
        lambda: SimpleNamespace(health_payload=lambda _settings: {"ok": True, "service": "module2"}),
    )
    monkeypatch.setattr(
        "app.modules.module4.composition.build_health_payload",
        _fake_module4_health_payload,
    )

    payload = asyncio.run(build_gateway_health(settings))

    assert payload["ok"] is True
    assert payload["upstreams"]["module4"]["mode"] == "local"
    assert payload["upstreams"]["module4"]["payload"]["status"] == "ok"
    assert payload["upstreams"]["module4"]["payload"]["service"] == "module4"


def test_gateway_health_treats_status_ok_payload_as_healthy(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class _FakeAuthService:
        async def health_payload(self) -> dict[str, object]:
            return {"ok": True, "service": "auth"}

    async def _fake_module4_health_payload(probe: str = "basic") -> dict[str, object]:
        assert probe == "basic"
        return {"status": "ok", "db_connected": True, "service": "module4"}

    monkeypatch.setattr(
        "app.services.gateway_service.get_auth_service",
        lambda: _FakeAuthService(),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_service",
        lambda: SimpleNamespace(health_payload=lambda _settings: {"ok": True, "service": "module2"}),
    )
    monkeypatch.setattr(
        "app.modules.module4.composition.build_health_payload",
        _fake_module4_health_payload,
    )

    payload = asyncio.run(build_gateway_health(settings))

    assert payload["ok"] is True
    assert payload["upstreams"]["module4"]["ok"] is True


def test_gateway_health_route_serializes_datetime_payload(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    app.include_router(gateway_router)
    app.dependency_overrides[get_settings] = lambda: settings

    async def _fake_gateway_health(_settings_obj: Settings) -> dict[str, object]:
        return {
            "ok": True,
            "upstreams": {
                "module4": {
                    "ok": True,
                    "payload": {
                        "last_success_at": datetime(2026, 4, 20, 1, 7, 36, tzinfo=timezone.utc),
                    },
                }
            },
            "frontend_static": {"ok": True},
        }

    monkeypatch.setattr(
        "app.modules.module4.api.endpoints.gateway.service.build_gateway_health",
        _fake_gateway_health,
    )

    with TestClient(app) as client:
        response = client.get("/gateway/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["upstreams"]["module4"]["payload"]["last_success_at"] == "2026-04-20T01:07:36+00:00"


def test_proxy_module4_request_targets_unified_gateway_base_url(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    monkeypatch.delenv("MODULE4_INTERNAL_TOKEN", raising=False)
    request = SimpleNamespace(
        headers={},
        query_params={},
        body=_empty_body,
    )
    captured: dict[str, object] = {}

    async def _fake_proxy_request(
        request_obj,
        settings_obj,
        upstream_base_url: str,
        upstream_path: str,
        *,
        additional_headers=None,
    ):
        del request_obj, settings_obj
        captured["base_url"] = upstream_base_url
        captured["path"] = upstream_path
        captured["headers"] = dict(additional_headers or {})
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.gateway_service.resolve_authenticated_tenant",
        lambda settings_obj, *, request, additional_headers=None, request_body=b"": SimpleNamespace(
            to_forward_headers=lambda: {
                "X-Authenticated-User-Id": "user-1",
                "X-Tenant-Id": "tenant-1",
            }
        ),
    )
    monkeypatch.setattr("app.services.gateway_service.proxy_request", _fake_proxy_request)

    payload = asyncio.run(
        proxy_module4_request(
            request,
            settings,
            "/module4/graph",
            additional_headers={"X-Trace-Id": "trace-1"},
        )
    )

    assert payload == {"ok": True}
    assert captured["base_url"] == "http://127.0.0.1:3001"
    assert captured["path"] == "/module4/graph"
    assert captured["headers"] == {
        "X-Trace-Id": "trace-1",
        "X-Authenticated-User-Id": "user-1",
        "X-Tenant-Id": "tenant-1",
    }


def test_proxy_module4_request_injects_internal_token_header(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    request = SimpleNamespace(
        headers={},
        query_params={},
        body=_empty_body,
    )
    captured: dict[str, str] = {}

    async def _fake_proxy_request(
        request_obj,
        settings_obj,
        upstream_base_url: str,
        upstream_path: str,
        *,
        additional_headers=None,
    ):
        del request_obj, settings_obj, upstream_base_url, upstream_path
        captured.update(dict(additional_headers or {}))
        return {"ok": True}

    monkeypatch.setenv("MODULE4_INTERNAL_TOKEN", "module4-internal-token")
    monkeypatch.setattr(
        "app.services.gateway_service.resolve_authenticated_tenant",
        lambda settings_obj, *, request, additional_headers=None, request_body=b"": SimpleNamespace(
            to_forward_headers=lambda: {
                "X-Authenticated-User-Id": "user-1",
                "X-Tenant-Id": "tenant-1",
            }
        ),
    )
    monkeypatch.setattr("app.services.gateway_service.proxy_request", _fake_proxy_request)

    payload = asyncio.run(proxy_module4_request(request, settings, "/module4/graph"))

    assert payload == {"ok": True}
    assert captured["X-Authenticated-User-Id"] == "user-1"
    assert captured["X-Tenant-Id"] == "tenant-1"
    assert captured["X-Module4-Internal-Token"] == "module4-internal-token"
