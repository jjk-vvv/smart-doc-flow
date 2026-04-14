from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, MutableMapping, Optional, Set


class Module4SyncTaskRuntime:
    """Track indexed module4 sync tasks and drain them safely on shutdown."""

    def __init__(self, *, logger: Any) -> None:
        self._logger = logger
        self._tasks: Set[asyncio.Task[Any]] = set()
        self._task_index: Dict[str, asyncio.Task[Any]] = {}

    def tasks_view(self) -> Set[asyncio.Task[Any]]:
        return self._tasks

    def index_view(self) -> MutableMapping[str, asyncio.Task[Any]]:
        return self._task_index

    def inflight_batch_count(self) -> int:
        return len(self._tasks)

    def inflight_outbox_count(self) -> int:
        return len(self._task_index)

    def get(self, outbox_id: str) -> Optional[asyncio.Task[Any]]:
        return self._task_index.get(str(outbox_id or "").strip())

    def clear_index(self) -> None:
        self._task_index.clear()

    def schedule_indexed(
        self,
        *,
        outbox_id: str,
        task_factory: Callable[[], asyncio.Task[Any]],
    ) -> Optional[asyncio.Task[Any]]:
        outbox_key = str(outbox_id or "").strip()
        if not outbox_key:
            return None
        current = self._task_index.get(outbox_key)
        if current and not current.done():
            return current
        return self.track(task_factory(), outbox_id=outbox_key)

    def track(self, task: asyncio.Task[Any], *, outbox_id: str = "") -> asyncio.Task[Any]:
        self._tasks.add(task)
        outbox_key = str(outbox_id or "").strip()
        if outbox_key:
            self._task_index[outbox_key] = task

        def _cleanup(done: asyncio.Task[Any]) -> None:
            self._tasks.discard(done)
            if outbox_key:
                current = self._task_index.get(outbox_key)
                if current is done:
                    self._task_index.pop(outbox_key, None)
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning("module2 module4 sync task crashed: %s: %s", type(exc).__name__, exc)

        task.add_done_callback(_cleanup)
        return task

    async def shutdown(self, *, drain_timeout: float) -> None:
        pending = list(self._tasks)
        if not pending:
            self._task_index.clear()
            return
        if drain_timeout > 0:
            _, still_pending = await asyncio.wait(pending, timeout=drain_timeout)
            if still_pending:
                for task in still_pending:
                    task.cancel()
                await asyncio.gather(*still_pending, return_exceptions=True)
        else:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        self._task_index.clear()
