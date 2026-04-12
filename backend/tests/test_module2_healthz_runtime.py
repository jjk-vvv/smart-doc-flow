from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


healthz_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "app_support_runtime.py"],
    "_smart_doc_flow_module2_healthz_runtime",
)

Module2HealthRuntime = healthz_runtime_module.Module2HealthRuntime


def test_module2_health_runtime_builds_expected_health_payload() -> None:
    runtime = Module2HealthRuntime()

    payload = runtime.build_payload(
        python_executable="python.exe",
        python_prefix="/venv",
        python_base_prefix="/python",
        python_venv_active=True,
        provider_diag={
            "ok": True,
            "checked_at": 12.5,
            "base_url": "https://provider-live.example",
            "model": "gpt-5-mini",
            "error": "",
        },
        provider_config={
            "configured": True,
            "provider_type": "openai_compatible",
            "base_url": "https://provider-config.example",
            "model": "fallback-model",
            "error": "config-error",
        },
        mineru_warmup={
            "enabled": True,
            "status": "completed",
            "ok": True,
            "started_at": 1.0,
            "finished_at": 2.0,
            "elapsed_sec": 1.0,
            "worker_count": 2,
            "detail": "ready",
            "error": "",
        },
        office_preview_jobs_in_memory=3,
        module4_sync_enabled=True,
        module4_sync_inflight_batches=4,
        module4_sync_inflight_outbox=5,
        module4_sync_metrics={
            "attempted_batches": 6,
            "succeeded_batches": 7,
            "failed_batches": 8,
            "last_error": "none",
            "last_job_id": "job-1",
            "last_batch_id": "batch-1",
            "last_endpoint": "/module4/ingest",
            "last_source_batch_key": "source-batch-1",
        },
        storage_diag={
            "db_connected": True,
            "degraded_memory_mode": False,
            "graph_sync_outbox_memory_size": 9,
        },
    )

    assert payload == {
        "status": "ok",
        "python_executable": "python.exe",
        "python_prefix": "/venv",
        "python_base_prefix": "/python",
        "python_venv_active": "true",
        "llm_provider_preflight_ok": "true",
        "llm_provider_last_checked_at": "12.5",
        "llm_provider_configured": "true",
        "llm_provider_type": "openai_compatible",
        "llm_provider_base_url": "https://provider-live.example",
        "llm_provider_model": "gpt-5-mini",
        "llm_provider_last_error": "config-error",
        "mineru_warmup_enabled": "true",
        "mineru_warmup_status": "completed",
        "mineru_warmup_ok": "true",
        "mineru_warmup_started_at": "1.0",
        "mineru_warmup_finished_at": "2.0",
        "mineru_warmup_elapsed_sec": "1.0",
        "mineru_warmup_worker_count": "2",
        "mineru_warmup_detail": "ready",
        "mineru_warmup_error": "",
        "office_preview_jobs_in_memory": "3",
        "module4_sync_enabled": "true",
        "module4_sync_inflight_batches": "4",
        "module4_sync_inflight_outbox": "5",
        "module4_sync_attempted_batches": "6",
        "module4_sync_succeeded_batches": "7",
        "module4_sync_failed_batches": "8",
        "module4_sync_last_error": "none",
        "module4_sync_last_job_id": "job-1",
        "module4_sync_last_batch_id": "batch-1",
        "module4_sync_last_endpoint": "/module4/ingest",
        "module4_sync_last_source_batch_key": "source-batch-1",
        "storage_db_connected": "true",
        "storage_degraded_memory_mode": "false",
        "storage_graph_sync_outbox_memory_size": "9",
    }


def test_module2_health_runtime_falls_back_to_config_and_defaults() -> None:
    runtime = Module2HealthRuntime()

    payload = runtime.build_payload(
        python_executable="",
        python_prefix="",
        python_base_prefix="",
        python_venv_active=False,
        provider_diag={},
        provider_config={
            "configured": False,
            "provider_type": "gemini",
            "base_url": "https://config.example",
            "model": "gemini-model",
            "error": "provider-missing",
        },
        mineru_warmup={},
        office_preview_jobs_in_memory=0,
        module4_sync_enabled=False,
        module4_sync_inflight_batches=0,
        module4_sync_inflight_outbox=0,
        module4_sync_metrics={},
        storage_diag={},
    )

    assert payload["python_venv_active"] == "false"
    assert payload["llm_provider_preflight_ok"] == "false"
    assert payload["llm_provider_configured"] == "false"
    assert payload["llm_provider_type"] == "gemini"
    assert payload["llm_provider_base_url"] == "https://config.example"
    assert payload["llm_provider_model"] == "gemini-model"
    assert payload["llm_provider_last_error"] == "provider-missing"
    assert payload["mineru_warmup_enabled"] == "false"
    assert payload["module4_sync_enabled"] == "false"
    assert payload["storage_db_connected"] == "false"
