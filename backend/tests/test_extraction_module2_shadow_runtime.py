from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from app.core.config import Settings
from app.modules.module2.core import module2_shadow_runtime as shadow_runtime


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


def test_write_json_file_atomic_retries_windows_replace_permission_error(monkeypatch, tmp_path: Path) -> None:
    target_path = tmp_path / "shadow" / "extract_job_demo123.json"
    original_replace = Path.replace
    replace_calls = {"count": 0}

    def flaky_replace(self: Path, target: Path) -> Path:
        if self.name.startswith("extract_job_demo123.json.tmp-") and Path(target) == target_path:
            replace_calls["count"] += 1
            if replace_calls["count"] < 3:
                raise PermissionError(5, "Access is denied")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    shadow_runtime._write_json_file_atomic(  # type: ignore[attr-defined]
        target_path,
        {"job_id": "extract_job_demo123", "status": "running"},
    )

    assert replace_calls["count"] == 3
    assert json.loads(target_path.read_text(encoding="utf-8"))["status"] == "running"


def test_upsert_shadow_payload_skips_duplicate_snapshot_save(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    saved_job_ids: list[str] = []
    payload = {
        "job_id": "extract_job_demo123",
        "status": "completed",
        "terminal": True,
        "updated_at": 123.0,
        "documents": [],
    }

    with shadow_runtime.extraction_shadow_lock:
        shadow_runtime.extraction_shadow_jobs.clear()
        shadow_runtime.extraction_shadow_pollers.clear()

    monkeypatch.setattr(
        shadow_runtime,
        "_save_shadow_snapshot",
        lambda _settings, job_id, _payload: saved_job_ids.append(job_id),
    )

    assert shadow_runtime._upsert_shadow_payload(settings, payload) is True  # type: ignore[attr-defined]
    assert shadow_runtime._upsert_shadow_payload(settings, dict(payload)) is True  # type: ignore[attr-defined]

    assert saved_job_ids == ["extract_job_demo123"]


def test_shadow_status_returns_snapshot_when_live_lookup_404_for_nonterminal_job(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    payload = {
        "job_id": "extract_job_demo404",
        "status": "running",
        "terminal": False,
        "updated_at": time.time(),
        "files": [{"file_name": "demo.docx", "status": "running"}],
        "errors": [],
    }

    with shadow_runtime.extraction_shadow_lock:
        shadow_runtime.extraction_shadow_jobs.clear()
        shadow_runtime.extraction_shadow_pollers.clear()
        shadow_runtime.extraction_shadow_live_backoff_until.clear()

    assert shadow_runtime._upsert_shadow_payload(settings, payload) is True  # type: ignore[attr-defined]

    result = shadow_runtime.get_shadow_extraction_job_status(
        settings,
        "extract_job_demo404",
        execution_facade_factory=lambda: SimpleNamespace(
            get_job_status=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                HTTPException(status_code=404, detail="Extraction job not found")
            )
        ),
        include_documents=False,
    )

    assert result["job_id"] == "extract_job_demo404"
    assert result["status"] == "running"
    assert result["terminal"] is False


def test_shadow_status_returns_snapshot_when_live_lookup_times_out(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    payload = {
        "job_id": "extract_job_demo_timeout",
        "status": "running",
        "terminal": False,
        "updated_at": time.time(),
        "files": [{"file_name": "demo.docx", "status": "running"}],
        "errors": [],
    }

    with shadow_runtime.extraction_shadow_lock:
        shadow_runtime.extraction_shadow_jobs.clear()
        shadow_runtime.extraction_shadow_pollers.clear()
        shadow_runtime.extraction_shadow_live_backoff_until.clear()

    monkeypatch.setattr(shadow_runtime, "_shadow_live_status_timeout_sec", lambda: 0.05)
    monkeypatch.setattr(shadow_runtime, "_shadow_live_status_backoff_sec", lambda: 1.0)
    assert shadow_runtime._upsert_shadow_payload(settings, payload) is True  # type: ignore[attr-defined]

    def _slow_get_job_status(*_args, **_kwargs):
        time.sleep(0.2)
        return {
            "job_id": "extract_job_demo_timeout",
            "status": "completed",
            "terminal": True,
            "updated_at": time.time(),
            "errors": [],
            "documents": [],
        }

    started = time.time()
    result = shadow_runtime.get_shadow_extraction_job_status(
        settings,
        "extract_job_demo_timeout",
        execution_facade_factory=lambda: SimpleNamespace(get_job_status=_slow_get_job_status),
        include_documents=False,
    )
    elapsed = time.time() - started

    assert result["job_id"] == "extract_job_demo_timeout"
    assert result["status"] == "running"
    assert elapsed < 0.15
    assert shadow_runtime._shadow_live_probe_in_backoff("extract_job_demo_timeout") is True  # type: ignore[attr-defined]
