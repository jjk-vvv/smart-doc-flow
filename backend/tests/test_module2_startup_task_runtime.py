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


startup_task_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "app_support_runtime.py"],
    "_smart_doc_flow_module2_startup_task_runtime",
)

StartupTaskRuntime = startup_task_runtime_module.StartupTaskRuntime


def test_startup_task_runtime_discards_finished_task() -> None:
    runtime = StartupTaskRuntime()

    async def _run() -> None:
        async def _done() -> str:
            return "ok"

        task = asyncio.create_task(_done())
        runtime.track(task)
        await task
        await asyncio.sleep(0)
        assert runtime.snapshot() == set()

    asyncio.run(_run())


def test_startup_task_runtime_cancels_pending_tasks_on_shutdown() -> None:
    runtime = StartupTaskRuntime()
    state = {"cancelled": 0}

    async def _run() -> None:
        async def _pending() -> None:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                state["cancelled"] += 1
                raise

        task1 = asyncio.create_task(_pending())
        task2 = asyncio.create_task(_pending())
        runtime.track(task1)
        runtime.track(task2)

        assert len(runtime.snapshot()) == 2
        await asyncio.sleep(0)
        await runtime.shutdown()
        assert state["cancelled"] == 2
        assert runtime.snapshot() == set()

    asyncio.run(_run())
