from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from app.core.config import Settings
from app.core.lifespan import lifespan_context
from app.modules.module4.core.module4_sidecar_runtime import (
    Module4SidecarManager,
    Module4SidecarSettings,
    resolve_live_module4_upstream_url,
)
from app.services.gateway_service import build_gateway_health, proxy_module4_request


def _settings(tmp_path: Path, *, upstream_url: str = "http://127.0.0.1:8100") -> Settings:
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
        module4_upstream_url=upstream_url,
    )


def _sidecar_settings(*, mode: str = "managed") -> Module4SidecarSettings:
    return Module4SidecarSettings(
        module4_port_hint="",
        module4_sidecar_mode=mode,
        module4_sidecar_python="",
        module4_sidecar_startup_timeout_sec=30.0,
    )


def test_module4_sidecar_health_payload_reports_remote_upstream_as_unmanageable(tmp_path: Path) -> None:
    settings = _settings(tmp_path, upstream_url="https://module4.example.com")
    manager = Module4SidecarManager(_sidecar_settings(mode="auto"))

    payload = manager.health_payload(settings)

    assert payload["requested_mode"] == "auto"
    assert payload["active_mode"] == "remote_upstream"
    assert payload["manageable"] is False


def test_module4_sidecar_ensure_ready_starts_managed_process_when_local_upstream_is_unhealthy(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = Module4SidecarManager(_sidecar_settings(mode="auto"))
    probe_calls = {"count": 0}
    start_calls: list[tuple[str, int, str]] = []

    def fake_probe(base_url: str, timeout_sec: float) -> dict[str, object]:
        del timeout_sec
        probe_calls["count"] += 1
        if probe_calls["count"] < 3:
            return {"ok": False, "base_url": base_url, "checked_at": 1.0, "error": "down"}
        return {"ok": True, "base_url": base_url, "checked_at": 2.0, "payload": {"status": "ok"}}

    def fake_start(settings_obj: Settings, host: str, port: int, base_url: str) -> None:
        del settings_obj
        start_calls.append((host, port, base_url))
        manager._process = SimpleNamespace(pid=5678, poll=lambda: None)
        manager._state.pid = 5678
        manager._state.base_url = base_url
        manager._state.started_by_manager = True
        manager._state.log_file = str(tmp_path / "module4-sidecar.log")

    monkeypatch.setattr(manager, "_probe_base_url", fake_probe)
    monkeypatch.setattr(manager, "_start_process_locked", fake_start)

    base_url = manager.ensure_ready(settings)
    payload = manager.health_payload(settings)

    assert base_url == "http://127.0.0.1:8100"
    assert start_calls == [("127.0.0.1", 8100, "http://127.0.0.1:8100")]
    assert payload["active_mode"] == "managed"
    assert payload["healthy"] is True


def test_resolve_live_module4_upstream_url_prefers_sidecar_when_requested(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        "app.modules.module4.core.module4_sidecar_runtime.get_module4_sidecar_manager",
        lambda: SimpleNamespace(ensure_ready=lambda _settings: "http://127.0.0.1:8100"),
    )

    resolved = resolve_live_module4_upstream_url(settings, ensure_sidecar=True, force_refresh=True)

    assert resolved == "http://127.0.0.1:8100"


def test_proxy_module4_request_prefers_sidecar_url(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    request = SimpleNamespace(
        headers={},
        query_params={},
        body=lambda: _empty_body(),
    )
    proxy_calls: list[tuple[str, str]] = []

    async def fake_proxy_request(
        request_obj,
        settings_obj,
        upstream_base_url: str,
        upstream_path: str,
        *,
        additional_headers=None,
    ):
        del request_obj, settings_obj
        assert additional_headers is not None
        proxy_calls.append((upstream_base_url, upstream_path))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.gateway_service.resolve_live_module4_upstream_url",
        lambda settings_obj, ensure_sidecar=False: "http://127.0.0.1:8100",
    )
    monkeypatch.setattr("app.services.gateway_service.proxy_request", fake_proxy_request)

    result = asyncio.run(
        proxy_module4_request(
            request,
            settings,
            "/module4/graph",
            additional_headers={"X-Authenticated-User-Id": "user-1"},
        )
    )

    assert result == {"ok": True}
    assert proxy_calls == [("http://127.0.0.1:8100", "/module4/graph")]


async def _empty_body() -> bytes:
    return b""


def test_gateway_health_includes_module4_sidecar_payload(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        "app.services.gateway_service.get_module4_sidecar_manager",
        lambda: SimpleNamespace(
            health_payload=lambda _settings: {
                "requested_mode": "managed",
                "active_mode": "managed",
                "healthy": True,
                "preferred_base_url": "http://127.0.0.1:8100",
                "probe": {
                    "ok": True,
                    "base_url": "http://127.0.0.1:8100",
                    "url": "http://127.0.0.1:8100/module4/healthz",
                    "status_code": 200,
                    "payload": {"status": "ok"},
                    "error": "",
                },
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.gateway_service.list_upstream_targets",
        lambda _settings: (
            SimpleNamespace(name="module4", base_url="http://127.0.0.1:8100", health_path="/module4/healthz", mode="upstream"),
        ),
    )

    payload = asyncio.run(build_gateway_health(settings))

    assert payload["ok"] is True
    assert payload["upstreams"]["module4"]["mode"] == "managed"
    assert payload["upstreams"]["module4"]["sidecar"]["requested_mode"] == "managed"


def test_module4_sidecar_health_payload_uses_bounded_probe_timeout(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        **{
            **_settings(tmp_path).__dict__,
            "request_timeout_sec": 300.0,
            "gateway_health_probe_timeout_sec": 2.0,
        }
    )
    manager = Module4SidecarManager(_sidecar_settings(mode="managed"))
    captured: dict[str, object] = {}

    def _fake_probe(base_url: str, timeout_sec: float) -> dict[str, object]:
        captured["base_url"] = base_url
        captured["timeout_sec"] = timeout_sec
        return {
            "ok": False,
            "base_url": base_url,
            "checked_at": 1.0,
            "error": "timeout",
        }

    monkeypatch.setattr(manager, "_probe_base_url", _fake_probe)

    payload = manager.health_payload(settings)

    assert payload["healthy"] is False
    assert captured == {
        "base_url": "http://127.0.0.1:8100",
        "timeout_sec": 2.0,
    }


def test_lifespan_context_manages_module4_sidecar_when_requested(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    events: list[str] = []

    async def _exercise() -> None:
        async with lifespan_context(app):
            events.append("inside")

    monkeypatch.setattr("app.core.lifespan.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.lifespan.get_extraction_settings", lambda: SimpleNamespace(module2_sidecar_mode="disabled"))
    monkeypatch.setattr(
        "app.core.lifespan.get_module2_sidecar_manager",
        lambda: SimpleNamespace(
            ensure_ready=lambda _settings: events.append("module2_ensure"),
            shutdown_started_process=lambda: events.append("module2_shutdown"),
        ),
    )
    monkeypatch.setattr(
        "app.core.lifespan.get_module4_sidecar_settings",
        lambda: SimpleNamespace(module4_sidecar_mode="managed"),
    )
    monkeypatch.setattr(
        "app.core.lifespan.get_module4_sidecar_manager",
        lambda: SimpleNamespace(
            ensure_ready=lambda _settings: events.append("module4_ensure"),
            shutdown_started_process=lambda: events.append("module4_shutdown"),
        ),
    )

    asyncio.run(_exercise())

    assert events == ["module4_ensure", "inside", "module2_shutdown", "module4_shutdown"]


def test_lifespan_context_continues_when_module4_prewarm_exceeds_grace(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        **{
            **_settings(tmp_path).__dict__,
            "gateway_startup_sidecar_grace_sec": 0.01,
        }
    )
    app = FastAPI()
    events: list[str] = []

    async def _exercise() -> None:
        async with lifespan_context(app):
            events.append("inside")

    def _slow_ensure(_settings) -> None:
        import time

        events.append("module4_ensure")
        time.sleep(0.05)

    monkeypatch.setattr("app.core.lifespan.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.lifespan.get_extraction_settings", lambda: SimpleNamespace(module2_sidecar_mode="disabled"))
    monkeypatch.setattr(
        "app.core.lifespan.get_module2_sidecar_manager",
        lambda: SimpleNamespace(
            ensure_ready=lambda _settings: events.append("module2_ensure"),
            shutdown_started_process=lambda: events.append("module2_shutdown"),
        ),
    )
    monkeypatch.setattr(
        "app.core.lifespan.get_module4_sidecar_settings",
        lambda: SimpleNamespace(module4_sidecar_mode="managed"),
    )
    monkeypatch.setattr(
        "app.core.lifespan.get_module4_sidecar_manager",
        lambda: SimpleNamespace(
            ensure_ready=_slow_ensure,
            shutdown_started_process=lambda: events.append("module4_shutdown"),
        ),
    )

    asyncio.run(_exercise())

    assert "inside" in events
    assert events[-2:] == ["module2_shutdown", "module4_shutdown"]
