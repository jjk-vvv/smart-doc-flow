from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.modules.extraction.module2_sidecar_runtime import (
    clear_module2_upstream_resolution_cache,
    module2_upstream_candidates,
    resolve_live_module2_upstream_url,
)


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=10.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


def test_module2_upstream_candidates_keep_configured_first_and_include_aliases(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.get_extraction_settings",
        lambda: type("ExtractionSettingsStub", (), {"module2_port_hint": ""})(),
    )
    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime._preferred_local_host_aliases",
        lambda: ["LAPTOP-A62ILD72", "10.13.59.152"],
    )

    candidates = module2_upstream_candidates(settings)

    assert candidates[0] == "http://127.0.0.1:8000"
    assert candidates[1] == "http://10.13.59.152:8000"
    assert candidates[2] == "http://LAPTOP-A62ILD72:8000"
    assert "http://127.0.0.1:8000" in candidates
    assert candidates.index("http://10.13.59.152:8000") < candidates.index("http://127.0.0.1:8010")
    assert candidates.index("http://LAPTOP-A62ILD72:8000") < candidates.index("http://127.0.0.1:8010")


def test_resolve_live_module2_upstream_url_prefers_healthy_host_alias(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    clear_module2_upstream_resolution_cache()

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.module2_upstream_candidates",
        lambda _settings: [
            "http://LAPTOP-A62ILD72:8000",
            "http://127.0.0.1:8000",
        ],
    )

    seen: list[str] = []

    def _fake_probe(base_url: str, timeout_sec: float) -> dict[str, object]:
        del timeout_sec
        seen.append(base_url)
        return {"ok": True, "base_url": base_url}

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.probe_module2_upstream",
        _fake_probe,
    )

    resolved = resolve_live_module2_upstream_url(settings, force_refresh=True)

    assert resolved == "http://LAPTOP-A62ILD72:8000"
    assert seen == ["http://LAPTOP-A62ILD72:8000"]


def test_resolve_live_module2_upstream_url_reuses_cached_loopback_url_without_reprobe(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    clear_module2_upstream_resolution_cache()

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.module2_upstream_candidates",
        lambda _settings: ["http://127.0.0.1:8000", "http://10.13.59.152:8000"],
    )

    seen: list[str] = []

    def _fake_probe(base_url: str, timeout_sec: float) -> dict[str, object]:
        del timeout_sec
        seen.append(base_url)
        return {"ok": base_url == "http://127.0.0.1:8000", "base_url": base_url}

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.probe_module2_upstream",
        _fake_probe,
    )

    first = resolve_live_module2_upstream_url(settings, force_refresh=True)
    second = resolve_live_module2_upstream_url(settings, force_refresh=False)

    assert first == "http://127.0.0.1:8000"
    assert second == first
    assert seen == ["http://127.0.0.1:8000"]


def test_resolve_live_module2_upstream_url_switches_cached_alias_back_to_loopback_when_healthy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    clear_module2_upstream_resolution_cache()

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.module2_upstream_candidates",
        lambda _settings: ["http://10.13.59.152:8000", "http://127.0.0.1:8000"],
    )

    seen: list[str] = []

    def _probe_with_alias_priority(base_url: str, timeout_sec: float) -> dict[str, object]:
        del timeout_sec
        seen.append(base_url)
        return {"ok": base_url == "http://10.13.59.152:8000", "base_url": base_url}

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.probe_module2_upstream",
        _probe_with_alias_priority,
    )
    resolved_alias = resolve_live_module2_upstream_url(settings, force_refresh=True)
    assert resolved_alias == "http://10.13.59.152:8000"

    def _probe_loopback_healthy(base_url: str, timeout_sec: float) -> dict[str, object]:
        del timeout_sec
        seen.append(base_url)
        return {"ok": base_url == "http://127.0.0.1:8000", "base_url": base_url}

    monkeypatch.setattr(
        "app.modules.extraction.module2_sidecar_runtime.probe_module2_upstream",
        _probe_loopback_healthy,
    )
    resolved_loopback = resolve_live_module2_upstream_url(settings, force_refresh=False)
    assert resolved_loopback == "http://127.0.0.1:8000"
    assert seen == ["http://10.13.59.152:8000", "http://127.0.0.1:8000"]
