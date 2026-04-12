from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.modules.extraction import module2_shadow_runtime as shadow_runtime


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
