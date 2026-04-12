from __future__ import annotations

import asyncio
import importlib.util
import sys
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


bootstrap_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "module2_bootstrap_runtime.py"],
    "_smart_doc_flow_module2_bootstrap_runtime",
)

Module2BootstrapRuntime = bootstrap_runtime_module.Module2BootstrapRuntime


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[object, ...]] = []

    def warning(self, *args) -> None:
        self.warnings.append(args)


class _FakeProviderPreflightRuntime:
    def __init__(self) -> None:
        self.build_config_calls: list[dict[str, object]] = []
        self.run_calls: list[dict[str, object]] = []
        self.snapshot_value: dict[str, object] = {"ok": True, "checked_at": 12.0}
        self.raise_error: Exception | None = None

    def snapshot(self) -> dict[str, object]:
        return dict(self.snapshot_value)

    def build_config_snapshot(self, *, timeout_sec: float, build_provider):
        self.build_config_calls.append({"timeout_sec": timeout_sec})
        provider = build_provider(timeout_sec)
        return {"configured": True, "provider": provider}

    def run_preflight(self, *, force: bool, ttl_sec: float, timeout_sec: float, build_provider):
        self.run_calls.append(
            {
                "force": force,
                "ttl_sec": ttl_sec,
                "timeout_sec": timeout_sec,
            }
        )
        if self.raise_error is not None:
            raise self.raise_error
        provider = build_provider(timeout_sec)
        return {"ok": True, "provider": provider}


class _FakeMineruWarmupRuntime:
    def __init__(self) -> None:
        self.snapshot_value: dict[str, object] = {"status": "idle"}
        self.calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        return dict(self.snapshot_value)

    async def startup_warmup_task(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


def _build_runtime(
    *,
    env: dict[str, str] | None = None,
    provider_runtime: _FakeProviderPreflightRuntime | None = None,
    mineru_runtime: _FakeMineruWarmupRuntime | None = None,
    logger: _FakeLogger | None = None,
    bounded_env_int=None,
    max_workers_provider=None,
) -> Module2BootstrapRuntime:
    env_map = dict(env or {})
    return Module2BootstrapRuntime(
        provider_preflight_runtime=provider_runtime or _FakeProviderPreflightRuntime(),
        mineru_warmup_runtime=mineru_runtime or _FakeMineruWarmupRuntime(),
        logger=logger or _FakeLogger(),
        getenv=lambda name, default="": env_map.get(name, default),
        bounded_env_int=bounded_env_int or (lambda name, default, minimum=1, maximum=8: default),
        max_workers_provider=max_workers_provider or (lambda: 6),
    )


def test_module2_bootstrap_runtime_builds_provider_snapshots_and_env_config() -> None:
    provider_runtime = _FakeProviderPreflightRuntime()
    mineru_runtime = _FakeMineruWarmupRuntime()
    runtime = _build_runtime(
        env={
            "MODULE2_PROVIDER_HEALTHCHECK_TTL_SEC": "90",
            "MODULE2_PROVIDER_HEALTHCHECK_TIMEOUT_SEC": "18",
            "MODULE2_PROVIDER_PREFLIGHT_ON_STARTUP": "true",
            "MODULE2_MINERU_WARMUP_ENABLE": "true",
            "MODULE2_MINERU_WARMUP_DELAY_SEC": "2.5",
            "MODULE2_MINERU_WARMUP_TIMEOUT_SEC": "88",
        },
        provider_runtime=provider_runtime,
        mineru_runtime=mineru_runtime,
        bounded_env_int=lambda name, default, minimum=1, maximum=8: 3,
        max_workers_provider=lambda: 7,
    )

    config = runtime.provider_config_snapshot(build_provider=lambda timeout_sec: f"provider:{timeout_sec}")
    preflight = runtime.run_provider_preflight(force=True, build_provider=lambda timeout_sec: f"provider:{timeout_sec}")

    assert runtime.provider_preflight_on_startup() is True
    assert runtime.mineru_warmup_enabled() is True
    assert runtime.mineru_warmup_delay_sec() == 2.5
    assert runtime.mineru_warmup_timeout_sec() == 88.0
    assert runtime.mineru_warmup_worker_count() == 3
    assert runtime.provider_preflight_snapshot() == {"ok": True, "checked_at": 12.0}
    assert runtime.mineru_warmup_snapshot() == {"status": "idle"}
    assert config == {"configured": True, "provider": "provider:18.0"}
    assert preflight == {"ok": True, "provider": "provider:18.0"}
    assert provider_runtime.build_config_calls == [{"timeout_sec": 18.0}]
    assert provider_runtime.run_calls == [{"force": True, "ttl_sec": 90.0, "timeout_sec": 18.0}]


def test_module2_bootstrap_runtime_ensure_provider_ready_raises_wrapped_error_when_required() -> None:
    provider_runtime = _FakeProviderPreflightRuntime()
    provider_runtime.raise_error = RuntimeError("provider down")
    logger = _FakeLogger()
    runtime = _build_runtime(
        env={
            "MODULE2_PROVIDER_HEALTHCHECK_ON_JOB_CREATE": "true",
            "MODULE2_FAIL_ON_PROVIDER_UNAVAILABLE": "true",
        },
        provider_runtime=provider_runtime,
        logger=logger,
    )

    async def _run() -> None:
        await runtime.ensure_provider_ready_for_job_create(
            build_provider=lambda timeout_sec: object(),
            raise_unavailable=lambda exc: RuntimeError(f"wrapped:{exc}"),
        )

    with pytest.raises(RuntimeError, match="wrapped:provider down"):
        asyncio.run(_run())

    assert len(logger.warnings) == 1
    assert logger.warnings[0][0] == "module2 provider preflight failed: %s: %s"
    assert logger.warnings[0][1] == "RuntimeError"
    assert str(logger.warnings[0][2]) == "provider down"


def test_module2_bootstrap_runtime_startup_provider_preflight_task_logs_failure_without_raising() -> None:
    provider_runtime = _FakeProviderPreflightRuntime()
    provider_runtime.raise_error = RuntimeError("startup boom")
    logger = _FakeLogger()
    runtime = _build_runtime(
        provider_runtime=provider_runtime,
        logger=logger,
    )

    async def _run() -> None:
        await runtime.startup_provider_preflight_task(
            build_provider=lambda timeout_sec: f"provider:{timeout_sec}"
        )

    asyncio.run(_run())

    assert provider_runtime.run_calls == [{"force": True, "ttl_sec": 120.0, "timeout_sec": 20.0}]
    assert len(logger.warnings) == 1
    assert logger.warnings[0][0] == "module2 startup provider preflight failed: %s: %s"
    assert logger.warnings[0][1] == "RuntimeError"
    assert str(logger.warnings[0][2]) == "startup boom"


def test_module2_bootstrap_runtime_starts_mineru_warmup_with_resolved_limits() -> None:
    mineru_runtime = _FakeMineruWarmupRuntime()
    runtime = _build_runtime(
        env={
            "MODULE2_MINERU_WARMUP_ENABLE": "true",
            "MODULE2_MINERU_WARMUP_DELAY_SEC": "1.25",
            "MODULE2_MINERU_WARMUP_TIMEOUT_SEC": "55",
        },
        mineru_runtime=mineru_runtime,
        bounded_env_int=lambda name, default, minimum=1, maximum=8: 2,
        max_workers_provider=lambda: 5,
    )

    async def _run_parse_in_process_pool(**kwargs) -> None:
        return None

    def _build_warmup_pdf_bytes() -> bytes:
        return b"%PDF-test"

    async def _run() -> None:
        await runtime.startup_mineru_warmup_task(
            run_parse_in_process_pool=_run_parse_in_process_pool,
            build_warmup_pdf_bytes=_build_warmup_pdf_bytes,
        )

    asyncio.run(_run())

    assert mineru_runtime.calls == [
        {
            "enabled": True,
            "worker_count": 2,
            "delay_sec": 1.25,
            "timeout_sec": 55.0,
            "build_warmup_pdf_bytes": _build_warmup_pdf_bytes,
            "run_parse_in_process_pool": _run_parse_in_process_pool,
        }
    ]
