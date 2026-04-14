from __future__ import annotations

import asyncio
import time
from threading import Lock
from typing import Any, Awaitable, Callable, Dict


BuildWarmupPdfBytes = Callable[[], bytes]
RunParseInProcessPool = Callable[..., Awaitable[Any]]


class MineruWarmupRuntime:
    """Manage MinerU startup warmup state and orchestration."""

    def __init__(self, *, logger: Any) -> None:
        self._logger = logger
        self._lock = Lock()
        self._state: Dict[str, Any] = {
            "enabled": False,
            "status": "idle",
            "ok": False,
            "started_at": 0.0,
            "finished_at": 0.0,
            "elapsed_sec": 0.0,
            "worker_count": 0,
            "detail": "",
            "error": "",
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _update_state(self, patch: Dict[str, Any]) -> None:
        with self._lock:
            self._state.update(dict(patch or {}))

    async def startup_warmup_task(
        self,
        *,
        enabled: bool,
        worker_count: int,
        delay_sec: float,
        timeout_sec: float,
        build_warmup_pdf_bytes: BuildWarmupPdfBytes,
        run_parse_in_process_pool: RunParseInProcessPool,
    ) -> None:
        self._update_state(
            {
                "enabled": bool(enabled),
                "worker_count": int(worker_count or 0),
            }
        )
        if not enabled:
            self._update_state(
                {
                    "status": "disabled",
                    "detail": "warmup_disabled_by_env",
                    "error": "",
                }
            )
            return

        if delay_sec > 0:
            await asyncio.sleep(delay_sec)

        started_at = time.time()
        self._update_state(
            {
                "status": "running",
                "ok": False,
                "started_at": started_at,
                "finished_at": 0.0,
                "elapsed_sec": 0.0,
                "detail": "warming_process_pool",
                "error": "",
                "worker_count": int(worker_count or 0),
            }
        )

        try:
            warmup_pdf_bytes = await asyncio.to_thread(build_warmup_pdf_bytes)
            loop = asyncio.get_running_loop()
            elapsed_samples = []
            for worker_index in range(int(worker_count or 0)):
                warm_t0 = time.perf_counter()
                await run_parse_in_process_pool(
                    loop=loop,
                    file_bytes=warmup_pdf_bytes,
                    file_name=f"module2_mineru_warmup_{worker_index + 1}.pdf",
                    track="VisualTrack",
                    timeout_sec=timeout_sec,
                    context_label=f"startup_mineru_warmup_{worker_index + 1}",
                )
                elapsed_samples.append(time.perf_counter() - warm_t0)

            finished_at = time.time()
            self._update_state(
                {
                    "status": "completed",
                    "ok": True,
                    "finished_at": finished_at,
                    "elapsed_sec": round(finished_at - started_at, 3),
                    "detail": (
                        f"warmed_workers={worker_count}; "
                        f"last_worker_sec={round(elapsed_samples[-1], 3) if elapsed_samples else 0.0}"
                    ),
                    "error": "",
                }
            )
            self._logger.info(
                "module2 MinerU warmup completed workers=%s elapsed=%.3fs",
                worker_count,
                finished_at - started_at,
            )
        except asyncio.CancelledError:
            finished_at = time.time()
            self._update_state(
                {
                    "status": "cancelled",
                    "ok": False,
                    "finished_at": finished_at,
                    "elapsed_sec": round(max(0.0, finished_at - started_at), 3),
                    "detail": "warmup_cancelled",
                }
            )
            raise
        except Exception as exc:
            finished_at = time.time()
            message = f"{type(exc).__name__}: {exc}"
            self._update_state(
                {
                    "status": "failed",
                    "ok": False,
                    "finished_at": finished_at,
                    "elapsed_sec": round(max(0.0, finished_at - started_at), 3),
                    "detail": "warmup_failed",
                    "error": message,
                }
            )
            self._logger.warning("module2 MinerU warmup failed: %s", message)
