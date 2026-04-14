from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import Response

from app.core.config import Settings
from app.modules.module2.core.assistant1_runtime import Assistant1Facade
from app.modules.module2.core.config import ExtractionSettings
from app.modules.module2.schemas.extraction import Assistant1ChatStreamRequest


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


def _extraction_settings(*, mode: str, fallback_to_legacy: bool) -> ExtractionSettings:
    return ExtractionSettings(
        module2_port_hint="",
        artifact_root_dir="",
        module2_execution_mode="auto",
        module2_fallback_to_upstream=True,
        module2_worker_timeout_sec=900.0,
        module2_worker_python="",
        module2_sidecar_mode="auto",
        module2_sidecar_python="",
        module2_sidecar_startup_timeout_sec=120.0,
        max_file_mb=25,
        doc_to_pdf_enable=True,
        office_preview_timeout_sec=120.0,
        office_preview_job_ttl_sec=1800.0,
        office_preview_job_cap=240,
        extract_job_ttl_sec=7200.0,
        extract_job_cap=240,
        shadow_poll_timeout_sec=2700.0,
        shadow_poll_interval_sec=1.2,
        assistant1_mode=mode,
        assistant1_fallback_to_legacy=fallback_to_legacy,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


def test_facade_health_payload_uses_legacy_when_native_is_not_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    legacy_runtime = SimpleNamespace(
        provider=SimpleNamespace(
            configured=True,
            model="gpt-5-mini",
            base_url="https://legacy.example.test",
            endpoint_path="/v1/responses",
        ),
        tavily=SimpleNamespace(settings=SimpleNamespace(tavily_api_key="tv-key")),
    )
    native_runtime = SimpleNamespace(
        health_payload=lambda _settings: {
            "ok": True,
            "configured": False,
            "runtime_ready": False,
            "model": "gpt-5-mini",
            "base_url": "https://native.example.test",
            "endpoint_path": "/v1/responses",
        }
    )
    facade = Assistant1Facade(
        _extraction_settings(mode="native", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: legacy_runtime,
        native_runtime=native_runtime,
    )

    payload = facade.health_payload(settings)

    assert payload["requested_mode"] == "native"
    assert payload["active_mode"] == "legacy"
    assert payload["fallback_active"] is True
    assert payload["configured"] is True
    assert payload["base_url"] == "https://legacy.example.test"


def test_facade_native_stream_falls_back_to_legacy_before_first_chunk(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class FailingNativeRuntime:
        def health_payload(self, _settings):
            return {"ok": True, "configured": True, "runtime_ready": True}

        async def stream_chat(self, **kwargs):
            del kwargs
            raise RuntimeError("native failed")
            yield b""  # pragma: no cover

    class LegacyRuntime:
        async def stream_chat(self, **kwargs):
            del kwargs
            yield b"legacy-chunk"

    facade = Assistant1Facade(
        _extraction_settings(mode="native", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: LegacyRuntime(),
        native_runtime=FailingNativeRuntime(),
    )
    payload = Assistant1ChatStreamRequest(message="hello", file_hash="hash-demo-1")

    async def collect() -> list[bytes]:
        return [chunk async for chunk in facade.stream_chat(settings, payload)]

    chunks = asyncio.run(collect())

    assert chunks == [b"legacy-chunk"]


def test_facade_native_not_ready_uses_legacy_without_invoking_native(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    native_calls: list[str] = []

    class NotReadyNativeRuntime:
        def health_payload(self, _settings):
            return {"ok": False, "configured": False, "runtime_ready": False}

        async def stream_chat(self, **kwargs):
            del kwargs
            native_calls.append("called")
            yield b"native-chunk"

    class LegacyRuntime:
        async def stream_chat(self, **kwargs):
            del kwargs
            yield b"legacy-chunk"

    facade = Assistant1Facade(
        _extraction_settings(mode="native", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: LegacyRuntime(),
        native_runtime=NotReadyNativeRuntime(),
    )
    payload = Assistant1ChatStreamRequest(message="hello", file_hash="hash-demo-1")

    async def collect() -> list[bytes]:
        return [chunk async for chunk in facade.stream_chat(settings, payload)]

    chunks = asyncio.run(collect())

    assert chunks == [b"legacy-chunk"]
    assert native_calls == []


def test_facade_missing_native_context_uses_legacy_without_invoking_native(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    native_calls: list[str] = []

    class NoContextNativeRuntime:
        def health_payload(self, _settings):
            return {"ok": True, "configured": True, "runtime_ready": True}

        def request_readiness_payload(self, _settings, *, file_hash: str = ""):
            return {
                "ok": False,
                "runtime_ready": True,
                "context_required": bool(file_hash),
                "context_found": False,
                "fallback_recommended": True,
            }

        async def stream_chat(self, **kwargs):
            del kwargs
            native_calls.append("called")
            yield b"native-chunk"

    class LegacyRuntime:
        async def stream_chat(self, **kwargs):
            del kwargs
            yield b"legacy-chunk"

    facade = Assistant1Facade(
        _extraction_settings(mode="native", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: LegacyRuntime(),
        native_runtime=NoContextNativeRuntime(),
    )
    payload = Assistant1ChatStreamRequest(message="hello", file_hash="hash-demo-1")

    async def collect() -> list[bytes]:
        return [chunk async for chunk in facade.stream_chat(settings, payload)]

    chunks = asyncio.run(collect())

    assert chunks == [b"legacy-chunk"]
    assert native_calls == []


def test_facade_legacy_stream_forwards_extra_context(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    seen: dict[str, object] = {}

    class LegacyRuntime:
        async def stream_chat(self, **kwargs):
            seen.update(kwargs)
            yield b"legacy-chunk"

    facade = Assistant1Facade(
        _extraction_settings(mode="legacy", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: LegacyRuntime(),
        native_runtime=SimpleNamespace(
            health_payload=lambda _settings: {"ok": True, "configured": True, "runtime_ready": True}
        ),
    )
    payload = Assistant1ChatStreamRequest(
        message="hello",
        file_hash="hash-demo-1",
        extra_context={
            "current_document": {
                "file_name": "demo.pdf",
                "top_fields": [{"label": "统计年份", "value": "2021"}],
            }
        },
    )

    async def collect() -> list[bytes]:
        return [chunk async for chunk in facade.stream_chat(settings, payload)]

    chunks = asyncio.run(collect())

    assert chunks == [b"legacy-chunk"]
    assert seen["extra_context"] == payload.extra_context


def test_facade_health_payload_uses_upstream_when_requested(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Assistant1Facade(
        _extraction_settings(mode="upstream", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: SimpleNamespace(
            provider=SimpleNamespace(configured=True, model="legacy-model", base_url="https://legacy.example", endpoint_path="/v1/responses"),
            tavily=SimpleNamespace(settings=SimpleNamespace(tavily_api_key="tv-key")),
        ),
        native_runtime=SimpleNamespace(
            health_payload=lambda _settings: {"ok": True, "configured": True, "runtime_ready": True, "model": "native-model"}
        ),
        upstream_runtime=SimpleNamespace(
            health_payload=lambda _settings: {
                "ok": True,
                "configured": True,
                "runtime_ready": True,
                "base_url": "http://127.0.0.1:8000",
                "endpoint_path": "/extract/assistant1/chat/stream",
                "transport": "module2_upstream",
            }
        ),
    )

    payload = facade.health_payload(settings)

    assert payload["requested_mode"] == "upstream"
    assert payload["active_mode"] == "upstream"
    assert payload["ok"] is True
    assert payload["base_url"] == "http://127.0.0.1:8000"
    assert payload["upstream"]["transport"] == "module2_upstream"


def test_facade_build_stream_response_delegates_to_upstream_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    seen: dict[str, object] = {}

    class UpstreamRuntime:
        def health_payload(self, _settings):
            return {"ok": True, "configured": True, "runtime_ready": True}

        def build_stream_response(self, _settings, *, request, payload, additional_headers=None):
            seen["path"] = str(request.url.path)
            seen["message"] = payload.message
            seen["headers"] = dict(additional_headers or {})
            return Response(content=b"ok", media_type="text/plain")

    facade = Assistant1Facade(
        _extraction_settings(mode="upstream", fallback_to_legacy=True),
        legacy_runtime_factory=lambda: SimpleNamespace(),
        native_runtime=SimpleNamespace(health_payload=lambda _settings: {"ok": True, "configured": True, "runtime_ready": True}),
        upstream_runtime=UpstreamRuntime(),
    )
    payload = Assistant1ChatStreamRequest(message="hello", file_hash="hash-demo-1")
    request = SimpleNamespace(url=SimpleNamespace(path="/extract/assistant1/chat/stream"))

    response = facade.build_stream_response(
        settings,
        request=request,  # type: ignore[arg-type]
        payload=payload,
        additional_headers={"x-tenant-id": "tenant-a"},
    )

    assert isinstance(response, Response)
    assert seen["path"] == "/extract/assistant1/chat/stream"
    assert seen["message"] == "hello"
    assert seen["headers"] == {"x-tenant-id": "tenant-a"}
