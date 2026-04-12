from __future__ import annotations

import asyncio
import time
from threading import Lock
from typing import Any, Awaitable, Callable, Dict, Set


AsyncCallback = Callable[[], Awaitable[Any]]
BuildProvider = Callable[[float], Any]
ShutdownProcessPool = Callable[[], None]
TrackTask = Callable[[asyncio.Task[Any]], None]


class StartupTaskRuntime:
    """Track startup background tasks and drain them safely on shutdown."""

    def __init__(self) -> None:
        self._tasks: Set[asyncio.Task[Any]] = set()

    def track(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(lambda finished: self._tasks.discard(finished))

    def snapshot(self) -> Set[asyncio.Task[Any]]:
        return set(self._tasks)

    async def shutdown(self) -> None:
        pending_tasks = list(self._tasks)
        if not pending_tasks:
            return
        for task in pending_tasks:
            task.cancel()
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        self._tasks.clear()


class Module2AppLifecycleRuntime:
    """Coordinate module2 startup and shutdown without owning business logic."""

    async def startup(
        self,
        *,
        connect_storage: AsyncCallback,
        recover_module4_sync_outbox: AsyncCallback,
        recover_extraction_jobs: AsyncCallback,
        provider_preflight_on_startup: bool,
        startup_provider_preflight_task: AsyncCallback,
        startup_mineru_warmup_task: AsyncCallback,
        track_startup_task: TrackTask,
    ) -> None:
        await connect_storage()
        await recover_module4_sync_outbox()
        await recover_extraction_jobs()

        if provider_preflight_on_startup:
            track_startup_task(
                asyncio.create_task(
                    startup_provider_preflight_task(),
                    name="module2-startup-provider-preflight",
                )
            )

        track_startup_task(
            asyncio.create_task(
                startup_mineru_warmup_task(),
                name="module2-startup-mineru-warmup",
            )
        )

    async def shutdown(
        self,
        *,
        shutdown_startup_tasks: AsyncCallback,
        shutdown_extraction_job_runtime: AsyncCallback,
        shutdown_module4_sync_tasks: AsyncCallback,
        close_storage: AsyncCallback,
        shutdown_process_pool: ShutdownProcessPool,
    ) -> None:
        await shutdown_startup_tasks()
        await shutdown_extraction_job_runtime()
        await shutdown_module4_sync_tasks()
        await close_storage()
        shutdown_process_pool()


class Module2HealthRuntime:
    """Build the module2 /healthz payload from already-collected subsystem snapshots."""

    @staticmethod
    def build_payload(
        *,
        python_executable: str,
        python_prefix: str,
        python_base_prefix: str,
        python_venv_active: bool,
        provider_diag: Dict[str, Any],
        provider_config: Dict[str, Any],
        mineru_warmup: Dict[str, Any],
        office_preview_jobs_in_memory: int,
        module4_sync_enabled: bool,
        module4_sync_inflight_batches: int,
        module4_sync_inflight_outbox: int,
        module4_sync_metrics: Dict[str, Any],
        storage_diag: Dict[str, Any],
    ) -> Dict[str, str]:
        provider_diag_data = dict(provider_diag or {})
        provider_config_data = dict(provider_config or {})
        mineru_data = dict(mineru_warmup or {})
        module4_metrics_data = dict(module4_sync_metrics or {})
        storage_data = dict(storage_diag or {})

        return {
            "status": "ok",
            "python_executable": str(python_executable or ""),
            "python_prefix": str(python_prefix or ""),
            "python_base_prefix": str(python_base_prefix or ""),
            "python_venv_active": str(bool(python_venv_active)).lower(),
            "llm_provider_preflight_ok": str(bool(provider_diag_data.get("ok"))).lower(),
            "llm_provider_last_checked_at": str(provider_diag_data.get("checked_at", 0.0) or 0.0),
            "llm_provider_configured": str(bool(provider_config_data.get("configured"))).lower(),
            "llm_provider_type": str(provider_config_data.get("provider_type", "") or ""),
            "llm_provider_base_url": str(
                provider_diag_data.get("base_url", "") or provider_config_data.get("base_url", "") or ""
            ),
            "llm_provider_model": str(
                provider_diag_data.get("model", "") or provider_config_data.get("model", "") or ""
            ),
            "llm_provider_last_error": str(
                provider_diag_data.get("error", "") or provider_config_data.get("error", "") or ""
            ),
            "mineru_warmup_enabled": str(bool(mineru_data.get("enabled"))).lower(),
            "mineru_warmup_status": str(mineru_data.get("status", "") or ""),
            "mineru_warmup_ok": str(bool(mineru_data.get("ok"))).lower(),
            "mineru_warmup_started_at": str(mineru_data.get("started_at", 0.0) or 0.0),
            "mineru_warmup_finished_at": str(mineru_data.get("finished_at", 0.0) or 0.0),
            "mineru_warmup_elapsed_sec": str(mineru_data.get("elapsed_sec", 0.0) or 0.0),
            "mineru_warmup_worker_count": str(mineru_data.get("worker_count", 0) or 0),
            "mineru_warmup_detail": str(mineru_data.get("detail", "") or ""),
            "mineru_warmup_error": str(mineru_data.get("error", "") or ""),
            "office_preview_jobs_in_memory": str(int(office_preview_jobs_in_memory or 0)),
            "module4_sync_enabled": str(bool(module4_sync_enabled)).lower(),
            "module4_sync_inflight_batches": str(int(module4_sync_inflight_batches or 0)),
            "module4_sync_inflight_outbox": str(int(module4_sync_inflight_outbox or 0)),
            "module4_sync_attempted_batches": str(module4_metrics_data.get("attempted_batches", 0) or 0),
            "module4_sync_succeeded_batches": str(module4_metrics_data.get("succeeded_batches", 0) or 0),
            "module4_sync_failed_batches": str(module4_metrics_data.get("failed_batches", 0) or 0),
            "module4_sync_last_error": str(module4_metrics_data.get("last_error", "") or ""),
            "module4_sync_last_job_id": str(module4_metrics_data.get("last_job_id", "") or ""),
            "module4_sync_last_batch_id": str(module4_metrics_data.get("last_batch_id", "") or ""),
            "module4_sync_last_endpoint": str(module4_metrics_data.get("last_endpoint", "") or ""),
            "module4_sync_last_source_batch_key": str(module4_metrics_data.get("last_source_batch_key", "") or ""),
            "storage_db_connected": str(storage_data.get("db_connected", False)).lower(),
            "storage_degraded_memory_mode": str(storage_data.get("degraded_memory_mode", False)).lower(),
            "storage_graph_sync_outbox_memory_size": str(storage_data.get("graph_sync_outbox_memory_size", 0)),
        }


class ProviderPreflightRuntime:
    """Manage provider preflight state, caching, and healthcheck updates."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state: Dict[str, Any] = {
            "ok": False,
            "checked_at": 0.0,
            "base_url": "",
            "model": "",
            "error": "",
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _update_state(self, patch: Dict[str, Any]) -> None:
        with self._lock:
            self._state.update(dict(patch or {}))

    def build_config_snapshot(
        self,
        *,
        timeout_sec: float,
        build_provider: BuildProvider,
    ) -> Dict[str, Any]:
        try:
            provider = build_provider(timeout_sec)
        except Exception as exc:
            return {
                "configured": False,
                "provider_type": "",
                "base_url": "",
                "model": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
        resolved_base_url = str(
            getattr(provider, "native_api_url", "") or getattr(provider, "base_url", "") or ""
        )
        return {
            "configured": bool(getattr(provider, "configured", False)),
            "provider_type": str(type(provider).__name__ or ""),
            "base_url": resolved_base_url,
            "model": str(getattr(provider, "model", "") or ""),
            "error": "",
        }

    def run_preflight(
        self,
        *,
        force: bool,
        ttl_sec: float,
        timeout_sec: float,
        build_provider: BuildProvider,
    ) -> Dict[str, Any]:
        now_ts = time.time()
        cached_state = self.snapshot()
        cached_ok = bool(cached_state.get("ok"))
        checked_at = float(cached_state.get("checked_at", 0.0) or 0.0)
        if (not force) and cached_ok and (now_ts - checked_at) < ttl_sec:
            return cached_state

        provider = build_provider(timeout_sec)
        if not provider.configured:
            message = "module2 extraction provider is not fully configured"
            self._update_state(
                {
                    "ok": False,
                    "checked_at": time.time(),
                    "base_url": getattr(provider, "base_url", ""),
                    "model": getattr(provider, "model", ""),
                    "error": message,
                }
            )
            raise RuntimeError(message)

        try:
            result = provider.healthcheck(timeout_sec=timeout_sec)
        except Exception as exc:
            message = str(exc or "").strip() or f"{type(exc).__name__}"
            self._update_state(
                {
                    "ok": False,
                    "checked_at": time.time(),
                    "base_url": provider.base_url,
                    "model": provider.model,
                    "error": message,
                }
            )
            raise

        self._update_state(
            {
                "ok": True,
                "checked_at": float(result.get("checked_at", time.time()) or time.time()),
                "base_url": str(result.get("base_url", "") or provider.base_url),
                "model": str(result.get("model", "") or provider.model),
                "error": "",
            }
        )
        return self.snapshot()
