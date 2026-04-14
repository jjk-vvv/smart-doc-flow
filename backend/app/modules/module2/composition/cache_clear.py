from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, MutableMapping, Optional, Set


ArtifactRootFactory = Callable[[], Path]
ResolveModule2PathFn = Callable[[str, Path], Path]
ExtractionJobStateRootFactory = Callable[[], Path]
ClearOfficePreviewRuntimeFn = Callable[..., Awaitable[None]]
ClearRuntimeCacheFn = Callable[..., Awaitable[Dict[str, Any]]]
ClearMineruProcessRuntimeCacheFn = Callable[[], None]
ResetProcessPoolFn = Callable[[str], int]


class Module2CacheClearRuntime:
    def __init__(
        self,
        *,
        module2_root: Path,
        artifact_root_factory: ArtifactRootFactory,
        resolve_module2_path: ResolveModule2PathFn,
        extraction_job_state_root_factory: ExtractionJobStateRootFactory,
    ) -> None:
        self._module2_root = Path(module2_root).resolve()
        self._artifact_root_factory = artifact_root_factory
        self._resolve_module2_path = resolve_module2_path
        self._extraction_job_state_root_factory = extraction_job_state_root_factory

    @staticmethod
    def _path_is_under(child: Path, root: Path) -> bool:
        try:
            child.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False

    def _clear_directory_contents(self, root: Path, *, preserve: Optional[Set[Path]] = None) -> int:
        root.mkdir(parents=True, exist_ok=True)
        preserved_paths: Set[Path] = set()
        for item in preserve or set():
            try:
                preserved_paths.add(item.resolve())
            except Exception:
                preserved_paths.add(item)
        removed = 0
        for child in root.iterdir():
            try:
                try:
                    child_resolved = child.resolve()
                except Exception:
                    child_resolved = child
                if child_resolved in preserved_paths:
                    continue
                if child.is_dir():
                    nested_preserve = {
                        path
                        for path in preserved_paths
                        if path != child_resolved and self._path_is_under(path, child_resolved)
                    }
                    if nested_preserve:
                        removed += self._clear_directory_contents(child_resolved, preserve=nested_preserve)
                    else:
                        shutil.rmtree(child, ignore_errors=True)
                        removed += 1
                elif child.is_file():
                    child.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                continue
        return removed

    def _mineru_runtime_models_dir(self) -> Path:
        configured = str(os.getenv("MODULE2_MINERU_RUNTIME_MODELS_DIR", "") or "").strip()
        default_root = (self._artifact_root_factory() / "pdf_parse" / "mineru_runtime_models").resolve()
        root = self._resolve_module2_path(configured, default_root) if configured else default_root
        root.mkdir(parents=True, exist_ok=True)
        return root

    def clear_materialized_dirs(self, *, scope: str) -> Dict[str, int]:
        normalized_scope = str(scope or "results").strip().lower() or "results"
        counts = {
            "removed_artifacts": 0,
            "removed_workdirs": 0,
            "removed_job_state": 0,
            "removed_runtime_models": 0,
        }

        artifact_root = self._artifact_root_factory()
        runtime_models_dir = self._mineru_runtime_models_dir()
        preserve_dirs: Set[Path] = set()
        if self._path_is_under(runtime_models_dir, artifact_root):
            preserve_dirs.add(runtime_models_dir)

        if normalized_scope in {"results", "all"}:
            counts["removed_artifacts"] = self._clear_directory_contents(artifact_root, preserve=preserve_dirs)
            counts["removed_workdirs"] = self._clear_directory_contents(self._module2_root / ".mcache")
            counts["removed_job_state"] = self._clear_directory_contents(self._extraction_job_state_root_factory())

        if normalized_scope in {"runtime", "all"}:
            counts["removed_runtime_models"] = self._clear_directory_contents(runtime_models_dir)

        return counts

    async def clear_extraction_runtime_state(
        self,
        *,
        extraction_job_tasks: MutableMapping[str, asyncio.Task[Any]],
        extraction_lock: asyncio.Lock,
        extraction_jobs: MutableMapping[str, Any],
        extraction_job_runtime_specs: MutableMapping[str, Dict[str, Any]],
        extraction_job_persist_markers: MutableMapping[str, float],
        clear_office_preview_runtime: ClearOfficePreviewRuntimeFn,
        tenant_id: str = "",
    ) -> None:
        normalized_tenant = str(tenant_id or "").strip()

        def _resolve_job_tenant(value: Any) -> str:
            if isinstance(value, dict):
                runtime_spec = value.get("runtime_spec") if isinstance(value.get("runtime_spec"), dict) else {}
                payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
                return str(
                    value.get("tenant_id")
                    or value.get("owner_id")
                    or runtime_spec.get("tenant_id")
                    or runtime_spec.get("owner_id")
                    or payload.get("tenant_id")
                    or payload.get("owner_id")
                    or ""
                ).strip()
            return str(getattr(value, "tenant_id", "") or getattr(value, "owner_id", "") or "").strip()

        if normalized_tenant:
            target_job_ids = [
                str(job_id)
                for job_id, job in extraction_jobs.items()
                if _resolve_job_tenant(job) == normalized_tenant
            ]
        else:
            target_job_ids = [str(job_id) for job_id in extraction_jobs.keys()]

        pending_tasks = [
            task
            for job_id, task in extraction_job_tasks.items()
            if str(job_id) in target_job_ids and not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        async with extraction_lock:
            for job_id in target_job_ids:
                extraction_jobs.pop(job_id, None)
                extraction_job_runtime_specs.pop(job_id, None)
                extraction_job_persist_markers.pop(job_id, None)
                extraction_job_tasks.pop(job_id, None)
        if normalized_tenant:
            try:
                await clear_office_preview_runtime(tenant_id=normalized_tenant)
            except TypeError:
                await clear_office_preview_runtime()
        else:
            await clear_office_preview_runtime()

    async def clear_module4_sync_runtime_state(
        self,
        *,
        module4_sync_tasks: Set[asyncio.Task[Any]],
        module4_sync_task_index: MutableMapping[str, asyncio.Task[Any]],
    ) -> None:
        pending_tasks = list(module4_sync_tasks)
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        module4_sync_tasks.clear()
        module4_sync_task_index.clear()

    async def clear_request(
        self,
        *,
        scope: str,
        tenant_id: str = "",
        extraction_job_tasks: MutableMapping[str, asyncio.Task[Any]],
        extraction_lock: asyncio.Lock,
        extraction_jobs: MutableMapping[str, Any],
        extraction_job_runtime_specs: MutableMapping[str, Dict[str, Any]],
        extraction_job_persist_markers: MutableMapping[str, float],
        clear_office_preview_runtime: ClearOfficePreviewRuntimeFn,
        module4_sync_tasks: Set[asyncio.Task[Any]],
        module4_sync_task_index: MutableMapping[str, asyncio.Task[Any]],
        clear_runtime_cache: ClearRuntimeCacheFn,
        clear_mineru_process_runtime_cache: ClearMineruProcessRuntimeCacheFn,
        reset_process_pool: ResetProcessPoolFn,
    ) -> Dict[str, Any]:
        normalized_scope = str(scope or "results").strip().lower() or "results"
        normalized_tenant = str(tenant_id or "").strip()

        await self.clear_extraction_runtime_state(
            extraction_job_tasks=extraction_job_tasks,
            extraction_lock=extraction_lock,
            extraction_jobs=extraction_jobs,
            extraction_job_runtime_specs=extraction_job_runtime_specs,
            extraction_job_persist_markers=extraction_job_persist_markers,
            clear_office_preview_runtime=clear_office_preview_runtime,
            tenant_id=normalized_tenant,
        )
        if not normalized_tenant:
            await self.clear_module4_sync_runtime_state(
                module4_sync_tasks=module4_sync_tasks,
                module4_sync_task_index=module4_sync_task_index,
            )

        cache_counts: Dict[str, Any] = {}
        if normalized_scope in {"results", "all"}:
            try:
                cache_counts = await clear_runtime_cache(tenant_id=normalized_tenant)
            except TypeError:
                cache_counts = await clear_runtime_cache()
        if normalized_scope in {"runtime", "all"} and not normalized_tenant:
            clear_mineru_process_runtime_cache()

        removed_materialized = (
            self.clear_materialized_dirs(scope=normalized_scope)
            if not normalized_tenant
            else {
                "removed_artifacts": 0,
                "removed_workdirs": 0,
                "removed_job_state": 0,
                "removed_runtime_models": 0,
            }
        )
        reset_generation = 0
        if normalized_scope in {"runtime", "all"} and not normalized_tenant:
            reset_generation = int(reset_process_pool(f"cache_clear:{normalized_scope}") or 0)

        return {
            "ok": True,
            "message": (
                f"模块二缓存已清理，scope={normalized_scope}"
                + (f", tenant={normalized_tenant}" if normalized_tenant else "")
            ),
            "scope": normalized_scope,
            "cache_counts": cache_counts,
            "removed_artifacts": int(removed_materialized.get("removed_artifacts", 0) or 0),
            "removed_runtime_models": int(removed_materialized.get("removed_runtime_models", 0) or 0),
            "removed_materialized": removed_materialized,
            "process_pool_reset_generation": reset_generation,
        }
