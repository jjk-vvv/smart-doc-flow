from __future__ import annotations

import asyncio
import threading
from queue import Queue

from app.modules.module2.composition import embedded_runtime


def test_run_sync_executes_without_active_event_loop() -> None:
    result = embedded_runtime._run_sync(asyncio.sleep(0, result=123))
    assert result == 123


def test_run_sync_executes_when_active_event_loop_exists() -> None:
    async def _scenario() -> str:
        return embedded_runtime._run_sync(asyncio.sleep(0, result="ok"))

    assert asyncio.run(_scenario()) == "ok"


def test_run_sync_worker_thread_reuses_primary_event_loop() -> None:
    async def _scenario() -> str:
        # Prime the embedded bridge with the currently running loop.
        assert embedded_runtime._run_sync(asyncio.sleep(0, result="primed")) == "primed"

        lock = asyncio.Lock()

        async def _use_lock() -> str:
            async with lock:
                await asyncio.sleep(0)
                return "ok"

        result_queue: Queue[object] = Queue(maxsize=1)

        def _worker() -> None:
            try:
                result_queue.put_nowait(embedded_runtime._run_sync(_use_lock()))
            except BaseException as exc:  # noqa: BLE001
                result_queue.put_nowait(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        await asyncio.to_thread(thread.join, 5)
        if thread.is_alive():
            raise AssertionError("worker thread did not complete")
        result = result_queue.get_nowait()
        if isinstance(result, BaseException):
            raise result
        return str(result)

    assert asyncio.run(_scenario()) == "ok"
