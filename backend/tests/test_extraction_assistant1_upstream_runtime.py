from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import Response, StreamingResponse

from app.core.config import Settings
from app.modules.extraction.assistant1_upstream_runtime import Assistant1UpstreamRuntime
from app.modules.extraction.schemas import Assistant1ChatStreamRequest


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=16,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


async def _collect_stream_body(response: StreamingResponse) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
    return b"".join(chunks)


class _FakeHeaders:
    def __init__(self, mapping: dict[str, str], *, set_cookies: list[str] | None = None) -> None:
        self._mapping = dict(mapping)
        self._set_cookies = list(set_cookies or [])

    def items(self):
        return self._mapping.items()

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._mapping.get(key, default)

    def get_all(self, key: str) -> list[str]:
        if str(key or "").lower() == "set-cookie":
            return list(self._set_cookies)
        return []


class _FakeStreamingUpstreamResponse:
    def __init__(self, body: bytes) -> None:
        self.status_code = 200
        self.headers = _FakeHeaders(
            {
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
            },
            set_cookies=["token=abc; Path=/; HttpOnly"],
        )
        self._body = bytes(body)
        self.closed = False

    def iter_content(self, chunk_size: int = 1):
        size = max(1, int(chunk_size or 1))
        for index in range(0, len(self._body), size):
            yield self._body[index:index + size]

    def close(self) -> None:
        self.closed = True


def test_upstream_runtime_returns_502_when_module2_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Assistant1UpstreamRuntime()

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.resolve_live_module2_upstream_url",
        lambda _settings, force_refresh=True: "",
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.probe_module2_upstream",
        lambda base_url, timeout_sec: {"ok": False, "base_url": base_url, "checked_at": 0.0},
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.get_module2_sidecar_manager",
        lambda: SimpleNamespace(ensure_ready=lambda _settings: (_ for _ in ()).throw(RuntimeError("sidecar unavailable"))),
    )

    response = runtime.build_stream_response(
        settings,
        request=SimpleNamespace(headers={}),  # type: ignore[arg-type]
        payload=Assistant1ChatStreamRequest(message="hello"),
        additional_headers={"x-tenant-id": "tenant-a"},
    )

    assert isinstance(response, Response)
    assert response.status_code == 502
    body = json.loads(response.body.decode("utf-8"))
    assert "Module2 assistant upstream unavailable" in body["detail"]


def test_upstream_runtime_streams_sse_bytes_without_rewriting(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Assistant1UpstreamRuntime()
    seen: dict[str, object] = {}
    upstream_response = _FakeStreamingUpstreamResponse(
        b'event: assistant.done\ndata: {"final_text":"ok from module2"}\n\n'
    )

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.resolve_live_module2_upstream_url",
        lambda _settings, force_refresh=True: "http://resolved-host:8000",
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.probe_module2_upstream",
        lambda base_url, timeout_sec: {
            "ok": str(base_url or "").strip() == "http://resolved-host:8000",
            "base_url": base_url,
            "checked_at": 123.0,
        },
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.get_module2_sidecar_manager",
        lambda: SimpleNamespace(ensure_ready=lambda _settings: (_ for _ in ()).throw(AssertionError("should not call ensure_ready"))),
    )

    def _fake_post(url, *, json=None, headers=None, timeout=None, stream=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = dict(headers or {})
        seen["timeout"] = timeout
        seen["stream"] = stream
        return upstream_response

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.requests.post",
        _fake_post,
    )

    response = runtime.build_stream_response(
        settings,
        request=SimpleNamespace(headers={"x-request-id": "req-123"}),  # type: ignore[arg-type]
        payload=Assistant1ChatStreamRequest(
            message="hello",
            session_id="sess-1",
            extra_context={"authenticated_user": {"id": "user-1"}},
        ),
        additional_headers={"x-tenant-id": "tenant-a"},
    )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache"
    assert "token=abc" in response.headers.get("set-cookie", "")

    body = asyncio.run(_collect_stream_body(response))

    assert body == b'event: assistant.done\ndata: {"final_text":"ok from module2"}\n\n'
    assert upstream_response.closed is True
    assert seen["url"] == "http://resolved-host:8000/extract/assistant1/chat/stream"
    assert seen["stream"] is True
    assert seen["json"] == {
        "message": "hello",
        "session_id": "sess-1",
        "file_hash": "",
        "history": [],
        "top_k": 5,
        "max_steps": 6,
        "debug": False,
        "resume_run_id": "",
        "after_seq": 0,
        "client_caps": {"supports_replace": True},
        "extra_context": {"authenticated_user": {"id": "user-1"}},
    }
    assert seen["headers"] == {
        "x-request-id": "req-123",
        "x-tenant-id": "tenant-a",
        "Accept": "text/event-stream",
    }


def test_upstream_runtime_fetches_session_via_resolved_live_upstream(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Assistant1UpstreamRuntime()
    seen: dict[str, object] = {}

    class _FakeJsonUpstreamResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = _FakeHeaders({"Content-Type": "application/json; charset=utf-8"})
            self.content = b'{"session_id":"sess-1","messages":[{"role":"assistant","content":"partial"}]}'
            self.closed = False

        def close(self) -> None:
            self.closed = True

    upstream_response = _FakeJsonUpstreamResponse()

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.resolve_live_module2_upstream_url",
        lambda _settings, force_refresh=True: "http://resolved-host:8000",
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.probe_module2_upstream",
        lambda base_url, timeout_sec: {
            "ok": True,
            "base_url": base_url,
            "checked_at": 123.0,
        },
    )

    def _fake_get(url, *, params=None, headers=None, timeout=None):
        seen["url"] = url
        seen["params"] = dict(params or {})
        seen["headers"] = dict(headers or {})
        seen["timeout"] = timeout
        return upstream_response

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.requests.get",
        _fake_get,
    )

    response = runtime.fetch_session_response(
        settings,
        request=SimpleNamespace(headers={"x-request-id": "req-456"}),  # type: ignore[arg-type]
        session_id="sess-1",
        limit=25,
        additional_headers={"x-tenant-id": "tenant-b"},
    )

    assert isinstance(response, Response)
    assert response.status_code == 200
    assert str(response.media_type or "").startswith("application/json")
    assert json.loads(response.body.decode("utf-8")) == {
        "session_id": "sess-1",
        "messages": [{"role": "assistant", "content": "partial"}],
    }
    assert upstream_response.closed is True
    assert seen["url"] == "http://resolved-host:8000/extract/assistant1/sessions/sess-1"
    assert seen["params"] == {"limit": 25}
    assert seen["headers"] == {
        "x-request-id": "req-456",
        "x-tenant-id": "tenant-b",
        "Accept": "application/json",
    }


def test_upstream_runtime_prefers_direct_module2_port_for_loopback_proxy(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Assistant1UpstreamRuntime()
    seen: dict[str, object] = {}
    upstream_response = _FakeStreamingUpstreamResponse(
        b'event: assistant.done\ndata: {"final_text":"ok from module2"}\n\n'
    )

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.resolve_live_module2_upstream_url",
        lambda _settings, force_refresh=True: "http://127.0.0.1:8000",
    )
    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.probe_module2_upstream",
        lambda base_url, timeout_sec: {
            "ok": str(base_url or "").strip() == "http://127.0.0.1:8000",
            "base_url": base_url,
            "checked_at": 123.0,
        },
    )

    def _fake_post(url, *, json=None, headers=None, timeout=None, stream=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = dict(headers or {})
        seen["timeout"] = timeout
        seen["stream"] = stream
        return upstream_response

    monkeypatch.setattr(
        "app.modules.extraction.assistant1_upstream_runtime.requests.post",
        _fake_post,
    )

    response = runtime.build_stream_response(
        settings,
        request=SimpleNamespace(headers={"x-request-id": "req-789"}),  # type: ignore[arg-type]
        payload=Assistant1ChatStreamRequest(message="hello"),
        additional_headers={"x-tenant-id": "tenant-c"},
    )

    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200
    body = asyncio.run(_collect_stream_body(response))
    assert body == b'event: assistant.done\ndata: {"final_text":"ok from module2"}\n\n'
    assert seen["url"] == "http://127.0.0.1:8010/extract/assistant1/chat/stream"
