from __future__ import annotations

import asyncio
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


app_lifecycle_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "app_support_runtime.py"],
    "_smart_doc_flow_module2_app_lifecycle_runtime",
)

Module2AppLifecycleRuntime = app_lifecycle_runtime_module.Module2AppLifecycleRuntime


def test_module2_app_lifecycle_runtime_runs_startup_and_tracks_background_tasks() -> None:
    runtime = Module2AppLifecycleRuntime()
    events: list[str] = []
    tracked: list[asyncio.Task[object]] = []

    async def _connect_storage() -> None:
        events.append("connect_storage")

    async def _recover_module4_sync_outbox() -> None:
        events.append("recover_module4_sync_outbox")

    async def _recover_extraction_jobs() -> None:
        events.append("recover_extraction_jobs")

    async def _startup_provider_preflight_task() -> None:
        events.append("startup_provider_preflight_task")

    async def _startup_mineru_warmup_task() -> None:
        events.append("startup_mineru_warmup_task")

    async def _run() -> None:
        await runtime.startup(
            connect_storage=_connect_storage,
            recover_module4_sync_outbox=_recover_module4_sync_outbox,
            recover_extraction_jobs=_recover_extraction_jobs,
            provider_preflight_on_startup=True,
            startup_provider_preflight_task=_startup_provider_preflight_task,
            startup_mineru_warmup_task=_startup_mineru_warmup_task,
            track_startup_task=tracked.append,
        )
        await asyncio.gather(*tracked)

    asyncio.run(_run())

    assert events[:3] == [
        "connect_storage",
        "recover_module4_sync_outbox",
        "recover_extraction_jobs",
    ]
    assert events[3:] == [
        "startup_provider_preflight_task",
        "startup_mineru_warmup_task",
    ]
    assert [task.get_name() for task in tracked] == [
        "module2-startup-provider-preflight",
        "module2-startup-mineru-warmup",
    ]


def test_module2_app_lifecycle_runtime_skips_provider_startup_task_when_disabled() -> None:
    runtime = Module2AppLifecycleRuntime()
    tracked: list[asyncio.Task[object]] = []
    events: list[str] = []

    async def _noop() -> None:
        return None

    async def _startup_provider_preflight_task() -> None:
        events.append("provider_should_not_run")

    async def _startup_mineru_warmup_task() -> None:
        events.append("mineru_warmup_ran")

    async def _run() -> None:
        await runtime.startup(
            connect_storage=_noop,
            recover_module4_sync_outbox=_noop,
            recover_extraction_jobs=_noop,
            provider_preflight_on_startup=False,
            startup_provider_preflight_task=_startup_provider_preflight_task,
            startup_mineru_warmup_task=_startup_mineru_warmup_task,
            track_startup_task=tracked.append,
        )
        await asyncio.gather(*tracked)

    asyncio.run(_run())

    assert events == ["mineru_warmup_ran"]
    assert [task.get_name() for task in tracked] == ["module2-startup-mineru-warmup"]


def test_module2_app_lifecycle_runtime_shutdown_preserves_order() -> None:
    runtime = Module2AppLifecycleRuntime()
    events: list[str] = []

    async def _shutdown_startup_tasks() -> None:
        events.append("shutdown_startup_tasks")

    async def _shutdown_extraction_job_runtime() -> None:
        events.append("shutdown_extraction_job_runtime")

    async def _shutdown_module4_sync_tasks() -> None:
        events.append("shutdown_module4_sync_tasks")

    async def _close_storage() -> None:
        events.append("close_storage")

    def _shutdown_process_pool() -> None:
        events.append("shutdown_process_pool")

    async def _run() -> None:
        await runtime.shutdown(
            shutdown_startup_tasks=_shutdown_startup_tasks,
            shutdown_extraction_job_runtime=_shutdown_extraction_job_runtime,
            shutdown_module4_sync_tasks=_shutdown_module4_sync_tasks,
            close_storage=_close_storage,
            shutdown_process_pool=_shutdown_process_pool,
        )

    asyncio.run(_run())

    assert events == [
        "shutdown_startup_tasks",
        "shutdown_extraction_job_runtime",
        "shutdown_module4_sync_tasks",
        "close_storage",
        "shutdown_process_pool",
    ]
