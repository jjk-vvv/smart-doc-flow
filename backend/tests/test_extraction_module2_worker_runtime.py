from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from app.core.config import Settings
from app.modules.extraction.config import ExtractionSettings
from app.modules.extraction.module2_worker_runtime import Module2WorkerRuntime


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


def _extraction_settings() -> ExtractionSettings:
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
        assistant1_mode="legacy",
        assistant1_fallback_to_legacy=True,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


def test_extract_batch_subprocess_serializes_request_files(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Module2WorkerRuntime(_extraction_settings())
    seen: dict[str, object] = {}

    async def fake_run_worker_command(*args, **kwargs):
        del args
        request_path = kwargs["request_path"]
        response_path = kwargs["response_path"]
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        seen["command"] = kwargs["command"]
        seen["tenant_id"] = request_payload["tenant_id"]
        seen["schema_form"] = request_payload["schema_form"]
        seen["file_payload"] = request_payload["files"][0]
        seen["response_path"] = str(response_path)
        serialized_path = Path(request_payload["files"][0]["path"])
        seen["serialized_exists"] = serialized_path.exists()
        seen["serialized_bytes"] = serialized_path.read_bytes()
        return {"ok": True, "result": {"documents": [{"file_name": "demo.pdf"}]}}

    monkeypatch.setattr(runtime, "run_worker_command", fake_run_worker_command)

    payload = asyncio.run(
        runtime.extract_batch_subprocess(
            settings,
            request_headers={"x-tenant-id": "tenant-a"},
            files_payload=[("files", ("source demo.pdf", b"%PDF-1.4", "application/pdf"))],
            schema_form='{"fields":["contract_amount"]}',
            tenant_id="tenant-a",
        )
    )

    assert payload["documents"][0]["file_name"] == "demo.pdf"
    assert seen["command"] == "extract-batch"
    assert seen["tenant_id"] == "tenant-a"
    assert seen["schema_form"] == '{"fields":["contract_amount"]}'
    assert seen["serialized_exists"] is True
    assert seen["serialized_bytes"] == b"%PDF-1.4"
    assert str(seen["file_payload"]["file_name"]) == "source demo.pdf"


def test_clear_cache_subprocess_serializes_scope(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = Module2WorkerRuntime(_extraction_settings())
    seen: dict[str, object] = {}

    async def fake_run_worker_command(*args, **kwargs):
        del args
        request_payload = json.loads(kwargs["request_path"].read_text(encoding="utf-8"))
        seen["command"] = kwargs["command"]
        seen["scope"] = request_payload["scope"]
        return {
            "ok": True,
            "result": {
                "ok": True,
                "message": "cleared",
                "scope": "all",
                "cache_counts": {"runtime": 1},
                "removed_materialized": {"artifacts": 2},
                "removed_artifacts": 3,
                "removed_runtime_models": 4,
                "process_pool_reset_generation": 5,
            },
        }

    monkeypatch.setattr(runtime, "run_worker_command", fake_run_worker_command)

    payload = asyncio.run(runtime.clear_cache_subprocess(settings, scope="all"))

    assert seen["command"] == "clear-cache"
    assert seen["scope"] == "all"
    assert payload["removed_artifacts"] == 3
    assert payload["removed_runtime_models"] == 4
    assert payload["process_pool_reset_generation"] == 5


def test_module2_compat_worker_script_imports_successfully() -> None:
    repo_root = Path(__file__).resolve().parents[1].parent
    worker_script = repo_root / "backend" / "app" / "modules" / "extraction" / "module2_compat_worker.py"
    script = "\n".join(
        [
            "import importlib.util",
            "from pathlib import Path",
            f"worker_script = Path({str(worker_script)!r})",
            "spec = importlib.util.spec_from_file_location('module2_compat_worker_check', worker_script)",
            "assert spec is not None and spec.loader is not None",
            "module = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(module)",
            "assert callable(module.main)",
            "print('ok')",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout
