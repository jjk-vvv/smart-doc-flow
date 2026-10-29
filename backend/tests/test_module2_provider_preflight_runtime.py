from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest


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


provider_preflight_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "app_support_runtime.py"],
    "_smart_doc_flow_module2_provider_preflight_runtime",
)

ProviderPreflightRuntime = provider_preflight_runtime_module.ProviderPreflightRuntime


class _ConfiguredProvider:
    def __init__(self, *, base_url: str = "https://llm.example", model: str = "model-x") -> None:
        self.configured = True
        self.base_url = base_url
        self.native_api_url = ""
        self.model = model
        self.healthcheck_calls: list[float] = []

    def healthcheck(self, *, timeout_sec: float):
        self.healthcheck_calls.append(timeout_sec)
        return {
            "checked_at": time.time(),
            "base_url": self.base_url,
            "model": self.model,
        }


class _UnconfiguredProvider:
    configured = False
    base_url = "https://llm.example"
    native_api_url = ""
    model = "model-x"


def test_provider_preflight_runtime_builds_config_snapshot() -> None:
    runtime = ProviderPreflightRuntime()
    snapshot = runtime.build_config_snapshot(
        timeout_sec=8.0,
        build_provider=lambda timeout_sec: _ConfiguredProvider(base_url="https://native.example", model="test-chat-model"),
    )

    assert snapshot == {
        "configured": True,
        "provider_type": "_ConfiguredProvider",
        "base_url": "https://native.example",
        "model": "test-chat-model",
        "error": "",
    }


def test_provider_preflight_runtime_builds_error_config_snapshot() -> None:
    runtime = ProviderPreflightRuntime()
    snapshot = runtime.build_config_snapshot(
        timeout_sec=8.0,
        build_provider=lambda timeout_sec: (_ for _ in ()).throw(RuntimeError("bad config")),
    )

    assert snapshot == {
        "configured": False,
        "provider_type": "",
        "base_url": "",
        "model": "",
        "error": "RuntimeError: bad config",
    }


def test_provider_preflight_runtime_returns_cached_success_within_ttl() -> None:
    runtime = ProviderPreflightRuntime()
    provider = _ConfiguredProvider()
    runtime.run_preflight(
        force=True,
        ttl_sec=120.0,
        timeout_sec=9.0,
        build_provider=lambda timeout_sec: provider,
    )

    cached = runtime.run_preflight(
        force=False,
        ttl_sec=120.0,
        timeout_sec=9.0,
        build_provider=lambda timeout_sec: (_ for _ in ()).throw(AssertionError("should not rebuild provider")),
    )

    assert cached["ok"] is True
    assert float(cached["checked_at"]) <= time.time()
    assert provider.healthcheck_calls == [9.0]


def test_provider_preflight_runtime_raises_when_provider_unconfigured() -> None:
    runtime = ProviderPreflightRuntime()

    with pytest.raises(RuntimeError, match="module2 extraction provider is not fully configured"):
        runtime.run_preflight(
            force=True,
            ttl_sec=120.0,
            timeout_sec=9.0,
            build_provider=lambda timeout_sec: _UnconfiguredProvider(),
        )

    snapshot = runtime.snapshot()
    assert snapshot["ok"] is False
    assert snapshot["base_url"] == "https://llm.example"
    assert snapshot["model"] == "model-x"
    assert snapshot["error"] == "module2 extraction provider is not fully configured"
    assert float(snapshot["checked_at"]) <= time.time()


def test_provider_preflight_runtime_updates_state_on_healthcheck_error() -> None:
    runtime = ProviderPreflightRuntime()

    class _BrokenProvider(_ConfiguredProvider):
        def healthcheck(self, *, timeout_sec: float):
            raise RuntimeError("health failed")

    with pytest.raises(RuntimeError, match="health failed"):
        runtime.run_preflight(
            force=True,
            ttl_sec=120.0,
            timeout_sec=9.0,
            build_provider=lambda timeout_sec: _BrokenProvider(),
        )

    snapshot = runtime.snapshot()
    assert snapshot["ok"] is False
    assert snapshot["base_url"] == "https://llm.example"
    assert snapshot["model"] == "model-x"
    assert snapshot["error"] == "health failed"
