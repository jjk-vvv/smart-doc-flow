from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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


module4_sync_config_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "module4_sync_config_runtime.py"],
    "_smart_doc_flow_module2_module4_sync_config_runtime",
)

Module4SyncConfigRuntime = module4_sync_config_runtime_module.Module4SyncConfigRuntime


def _build_runtime(env: dict[str, str] | None = None) -> Module4SyncConfigRuntime:
    mapping = dict(env or {})
    return Module4SyncConfigRuntime(env_get=lambda key, default="": mapping.get(key, default))


def test_module4_sync_config_runtime_uses_expected_defaults() -> None:
    runtime = _build_runtime()

    assert runtime.sync_enabled() is True
    assert runtime.document_sync_enabled() is False
    assert runtime.document_sync_per_file_enabled() is True
    assert runtime.document_sync_final_batch_enabled() is False
    assert runtime.payload_mode() == "hybrid"
    assert runtime.base_url() == "http://localhost:8100"
    assert runtime.timeout_sec() == 12.0
    assert runtime.retries() == 2
    assert runtime.backoff_sec() == 1.5
    assert runtime.shutdown_drain_sec() == 8.0
    assert runtime.default_tenant() == "default"


def test_module4_sync_config_runtime_clamps_and_normalizes_env_values() -> None:
    runtime = _build_runtime(
        {
            "MODULE2_MODULE4_SYNC_ENABLED": "no",
            "MODULE2_MODULE4_DOCUMENT_SYNC_ENABLED": "yes",
            "MODULE2_MODULE4_SYNC_PER_FILE_ENABLE": "0",
            "MODULE2_MODULE4_SYNC_FINAL_BATCH_ENABLE": "1",
            "MODULE2_MODULE4_SYNC_PAYLOAD_MODE": "text_corpus_only",
            "MODULE2_MODULE4_BASE_URL": " https://module4.example/ ",
            "MODULE2_MODULE4_SYNC_TIMEOUT_SEC": "1",
            "MODULE2_MODULE4_SYNC_RETRIES": "99",
            "MODULE2_MODULE4_SYNC_BACKOFF_SEC": "0",
            "MODULE2_MODULE4_SHUTDOWN_DRAIN_SEC": "-3",
            "MODULE2_MODULE4_DEFAULT_TENANT": " tenant-z ",
        }
    )

    assert runtime.sync_enabled() is False
    assert runtime.document_sync_enabled() is True
    assert runtime.document_sync_per_file_enabled() is False
    assert runtime.document_sync_final_batch_enabled() is True
    assert runtime.payload_mode() == "text_corpus_only"
    assert runtime.base_url() == "https://module4.example"
    assert runtime.timeout_sec() == 2.0
    assert runtime.retries() == 5
    assert runtime.backoff_sec() == 0.2
    assert runtime.shutdown_drain_sec() == 0.0
    assert runtime.default_tenant() == "tenant-z"


def test_module4_sync_config_runtime_resolves_tenant_and_headers() -> None:
    runtime = _build_runtime(
        {
            "MODULE2_MODULE4_DEFAULT_TENANT": "tenant-default",
            "MODULE2_MODULE4_BEARER_TOKEN": "token-123",
        }
    )
    request = SimpleNamespace(headers={"x-tenant-id": "tenant-header"})

    assert runtime.tenant(request, explicit="tenant-explicit") == "tenant-explicit"
    assert runtime.tenant(request) == "tenant-header"
    assert runtime.tenant(SimpleNamespace(headers={})) == "tenant-default"
    assert runtime.headers("tenant-h") == {
        "Content-Type": "application/json",
        "X-Tenant-Id": "tenant-h",
        "X-Authenticated-Tenant-Id": "tenant-h",
        "Authorization": "Bearer token-123",
    }


def test_module4_sync_config_runtime_retry_policy_matches_existing_behavior() -> None:
    runtime = _build_runtime({"MODULE2_MODULE4_SYNC_BACKOFF_SEC": "1.5"})

    assert runtime.retryable_status(408) is True
    assert runtime.retryable_status(503) is True
    assert runtime.retryable_status(404) is False
    assert runtime.delay_sec(1) == 1.5
    assert runtime.delay_sec(2) == 3.0
    assert runtime.delay_sec(10) == 12.0


def test_module4_sync_config_runtime_payload_mode_falls_back_for_invalid_value() -> None:
    runtime = _build_runtime({"MODULE2_MODULE4_SYNC_PAYLOAD_MODE": "legacy"})
    assert runtime.payload_mode() == "hybrid"
