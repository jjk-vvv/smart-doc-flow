from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.core.config import Settings
from app.modules.extraction.config import ExtractionSettings
from app.modules.extraction.module2_shadow_runtime import get_shadow_extraction_job_status
from app.modules.extraction.module2_sidecar_runtime import Module2SidecarManager, request_module2


def _settings(tmp_path: Path, *, upstream_url: str = "http://127.0.0.1:8010") -> Settings:
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
        module2_upstream_url=upstream_url,
        module4_upstream_url="http://127.0.0.1:8100",
    )


def _extraction_settings(*, mode: str = "auto") -> ExtractionSettings:
    return ExtractionSettings(
        module2_port_hint="",
        artifact_root_dir="",
        module2_execution_mode="upstream",
        module2_fallback_to_upstream=True,
        module2_worker_timeout_sec=900.0,
        module2_worker_python="",
        module2_sidecar_mode=mode,
        module2_sidecar_python="",
        module2_sidecar_startup_timeout_sec=30.0,
        max_file_mb=25,
        doc_to_pdf_enable=True,
        office_preview_timeout_sec=120.0,
        office_preview_job_ttl_sec=1800.0,
        office_preview_job_cap=240,
        extract_job_ttl_sec=7200.0,
        extract_job_cap=240,
        shadow_poll_timeout_sec=2700.0,
        shadow_poll_interval_sec=1.2,
        assistant1_mode="legacy",
        assistant1_fallback_to_legacy=True,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


def test_sidecar_health_payload_reports_remote_upstream_as_unmanageable(tmp_path: Path) -> None:
    settings = _settings(tmp_path, upstream_url="https://module2.example.com")
    manager = Module2SidecarManager(_extraction_settings(mode="auto"))

    payload = manager.health_payload(settings)

    assert payload["requested_mode"] == "auto"
    assert payload["active_mode"] == "remote_upstream"
    assert payload["manageable"] is False


def test_sidecar_ensure_ready_starts_managed_process_when_local_upstream_is_unhealthy(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = Module2SidecarManager(_extraction_settings(mode="auto"))
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
        manager._process = SimpleNamespace(pid=4321, poll=lambda: None)
        manager._state.pid = 4321
        manager._state.base_url = base_url
        manager._state.started_by_manager = True
        manager._state.log_file = str(tmp_path / "sidecar.log")

    monkeypatch.setattr(manager, "_probe_base_url", fake_probe)
    monkeypatch.setattr(manager, "_start_process_locked", fake_start)

    base_url = manager.ensure_ready(settings)
    payload = manager.health_payload(settings)

    assert base_url == "http://127.0.0.1:8010"
    assert start_calls == [("127.0.0.1", 8010, "http://127.0.0.1:8010")]
    assert payload["active_mode"] == "managed"
    assert payload["healthy"] is True


def test_request_module2_prefers_sidecar_url_when_enabled(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    request_calls: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.get_module2_sidecar_manager",
        lambda: SimpleNamespace(ensure_ready=lambda _settings: "http://127.0.0.1:8010"),
    )
    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.requests.request",
        lambda **kwargs: request_calls.append(kwargs) or FakeResponse(),
    )

    response = request_module2(settings, method="GET", path="/extract/jobs/status/demo", ensure_sidecar=True)

    assert response.status_code == 200
    assert request_calls[0]["url"] == "http://127.0.0.1:8010/extract/jobs/status/demo"


def test_job_shadow_status_requests_force_sidecar_ready(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade_calls: list[tuple[str, bool]] = []

    payload = get_shadow_extraction_job_status(
        settings,
        "extract_job_demo123",
        execution_facade_factory=lambda: SimpleNamespace(
            get_job_status=lambda _settings, *, job_id, include_documents=False: (
                facade_calls.append((job_id, include_documents))
                or {
                    "job_id": "extract_job_demo123",
                    "status": "completed",
                    "terminal": True,
                    "updated_at": 1.0,
                    "documents": [],
                    "errors": [],
                }
            )
        ),
        include_documents=False,
    )

    assert payload["job_id"] == "extract_job_demo123"
    assert facade_calls == [("extract_job_demo123", False)]
