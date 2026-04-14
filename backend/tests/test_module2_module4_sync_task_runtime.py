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


module4_sync_task_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "module4_sync_task_runtime.py"],
    "_smart_doc_flow_module2_module4_sync_task_runtime",
)

Module4SyncTaskRuntime = module4_sync_task_runtime_module.Module4SyncTaskRuntime


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[object, ...]] = []

    def warning(self, *args) -> None:
        self.warnings.append(args)


def test_module4_sync_task_runtime_tracks_and_discards_finished_task() -> None:
    logger = _FakeLogger()
    runtime = Module4SyncTaskRuntime(logger=logger)

    async def _run() -> None:
        async def _done() -> str:
            return "ok"

        task = asyncio.create_task(_done())
        runtime.track(task, outbox_id="box-1")
        assert runtime.get("box-1") is task
        assert runtime.inflight_batch_count() == 1
        assert runtime.inflight_outbox_count() == 1
        await task
        await asyncio.sleep(0)
        assert runtime.get("box-1") is None
        assert runtime.inflight_batch_count() == 0
        assert runtime.inflight_outbox_count() == 0

    asyncio.run(_run())


def test_module4_sync_task_runtime_schedule_indexed_deduplicates_running_task() -> None:
    logger = _FakeLogger()
    runtime = Module4SyncTaskRuntime(logger=logger)
    state = {"created": 0}

    async def _run() -> None:
        gate = asyncio.Event()

        async def _pending() -> None:
            await gate.wait()

        first = runtime.schedule_indexed(
            outbox_id="box-same",
            task_factory=lambda: _create_pending_task(_pending, state),
        )
        second = runtime.schedule_indexed(
            outbox_id="box-same",
            task_factory=lambda: _create_pending_task(_pending, state),
        )
        assert first is not None
        assert second is first
        assert state["created"] == 1
        gate.set()
        await asyncio.gather(first, return_exceptions=True)
        await asyncio.sleep(0)
        assert runtime.get("box-same") is None

    asyncio.run(_run())


def test_module4_sync_task_runtime_logs_crashed_task() -> None:
    logger = _FakeLogger()
    runtime = Module4SyncTaskRuntime(logger=logger)

    async def _run() -> None:
        async def _boom() -> None:
            raise RuntimeError("sync failed")

        task = asyncio.create_task(_boom())
        runtime.track(task, outbox_id="box-2")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)
        assert runtime.get("box-2") is None
        assert logger.warnings[-1][0] == "module2 module4 sync task crashed: %s: %s"
        assert logger.warnings[-1][1] == "RuntimeError"
        assert str(logger.warnings[-1][2]) == "sync failed"

    asyncio.run(_run())


def test_module4_sync_task_runtime_shutdown_cancels_pending_tasks_and_clears_index() -> None:
    logger = _FakeLogger()
    runtime = Module4SyncTaskRuntime(logger=logger)
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
        runtime.track(task1, outbox_id="box-a")
        runtime.track(task2, outbox_id="box-b")
        await asyncio.sleep(0)
        assert runtime.inflight_batch_count() == 2
        assert runtime.inflight_outbox_count() == 2
        await runtime.shutdown(drain_timeout=0.0)
        assert state["cancelled"] == 2
        assert runtime.inflight_outbox_count() == 0

    asyncio.run(_run())


def _create_pending_task(coro_factory, state: dict[str, int]) -> asyncio.Task[None]:
    state["created"] += 1
    return asyncio.create_task(coro_factory())
