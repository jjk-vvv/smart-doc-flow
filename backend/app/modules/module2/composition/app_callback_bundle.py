from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, MutableMapping

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse

from app.modules.file_assets.service import resolve_file_for_owner


AsyncCallback = Callable[[], Awaitable[Any]]
HealthPayloadFn = Callable[[], Dict[str, str]]
ClearCacheRequestFn = Callable[..., Awaitable[Dict[str, Any]]]
ServeArtifactFn = Callable[[str, str], Any]
ServeFileAssetFn = Callable[..., Any]
ScheduleModule4SyncOutboxFn = Callable[[Any], None]
RecoverPendingOutboxFn = Callable[..., Awaitable[None]]
RecoverExtractionJobsFn = Callable[[], Awaitable[None]]
BuildProviderFn = Callable[[], Any]
RunParseInProcessPoolFn = Callable[..., Awaitable[Any]]
ResetProcessPoolFn = Callable[[str], int]


@dataclass(frozen=True)
class Module2AppCallbackBundle:
    clear_cache_request: ClearCacheRequestFn
    serve_layout_preview: ServeArtifactFn
    serve_artifact: ServeArtifactFn
    serve_file_asset: ServeFileAssetFn
    build_health_payload: HealthPayloadFn
    startup: AsyncCallback
    shutdown: AsyncCallback


def build_module2_app_callback_bundle(
    *,
    app_lifecycle_runtime,
    cache_clear_runtime,
    artifact_file_runtime,
    health_runtime,
    module2_bootstrap_runtime,
    startup_task_runtime,
    runtime_state_repository: Any,
    office_preview_runtime,
    module4_sync_config_runtime,
    module4_sync_outbox_runtime,
    module4_sync_metrics_runtime,
    module4_sync_task_runtime,
    extraction_job_runtime,
    extraction_jobs: MutableMapping[str, Any],
    extraction_lock: asyncio.Lock,
    extraction_job_runtime_specs: MutableMapping[str, Dict[str, Any]],
    extraction_job_tasks: MutableMapping[str, asyncio.Task[Any]],
    extraction_job_persist_markers: MutableMapping[str, float],
    clear_mineru_process_runtime_cache,
    reset_process_pool: ResetProcessPoolFn,
    build_preflight_provider: BuildProviderFn,
    run_parse_in_process_pool: RunParseInProcessPoolFn,
    schedule_module4_sync_outbox: ScheduleModule4SyncOutboxFn,
    shutdown_process_pool: Callable[[], None],
    python_executable: str,
    python_prefix: str,
    python_base_prefix: str,
    python_venv_active: bool,
) -> Module2AppCallbackBundle:
    if runtime_state_repository is None:
        raise ValueError("runtime_state_repository is required")
    resolved_runtime_state_repository = runtime_state_repository

    async def _recover_module4_sync_outbox() -> None:
        if not module4_sync_config_runtime.sync_enabled():
            return
        await module4_sync_outbox_runtime.recover_pending_outbox(
            schedule_outbox=schedule_module4_sync_outbox,
            limit=200,
        )

    async def _recover_extraction_jobs() -> None:
        await extraction_job_runtime.recover_from_snapshots()

    async def _clear_cache_request(scope: str, *, tenant_id: str = "") -> Dict[str, Any]:
        return await cache_clear_runtime.clear_request(
            scope=scope,
            tenant_id=tenant_id,
            extraction_job_tasks=extraction_job_tasks,
            extraction_lock=extraction_lock,
            extraction_jobs=extraction_jobs,
            extraction_job_runtime_specs=extraction_job_runtime_specs,
            extraction_job_persist_markers=extraction_job_persist_markers,
            clear_office_preview_runtime=office_preview_runtime.clear,
            module4_sync_tasks=module4_sync_task_runtime.tasks_view(),
            module4_sync_task_index=module4_sync_task_runtime.index_view(),
            clear_runtime_cache=resolved_runtime_state_repository.clear_runtime_cache,
            clear_mineru_process_runtime_cache=clear_mineru_process_runtime_cache,
            reset_process_pool=reset_process_pool,
        )

    def _serve_layout_preview(artifact_name: str, request_method: str) -> Any:
        return artifact_file_runtime.serve_artifact(
            path_fragment=f"layout/{artifact_name}",
            request_method=request_method,
            not_found_detail=f"Layout preview not found: {artifact_name}",
            default_media_type="application/pdf",
        )

    def _serve_artifact(artifact_path: str, request_method: str) -> Any:
        return artifact_file_runtime.serve_artifact(
            path_fragment=artifact_path,
            request_method=request_method,
            not_found_detail=f"Artifact not found: {artifact_path}",
            default_media_type="application/octet-stream",
        )

    def _resolve_file_asset_owner_id(request: Any | None = None) -> str:
        authenticated_user = getattr(getattr(request, "state", None), "authenticated_user", None)
        from_state = (
            str(getattr(authenticated_user, "tenant_id", "") or "").strip()
            or str(getattr(authenticated_user, "user_id", "") or "").strip()
        )
        if from_state:
            return from_state

        headers = getattr(request, "headers", None)
        if headers is not None:
            from_headers = (
                str(headers.get("X-Authenticated-Tenant-Id") or "").strip()
                or str(headers.get("X-Tenant-Id") or "").strip()
                or str(headers.get("X-Authenticated-User-Id") or "").strip()
            )
            if from_headers:
                return from_headers

        return str(os.getenv("AUTH_TENANT_DEFAULT_ID", "default") or "").strip() or "default"

    def _serve_file_asset(file_id: str, request_method: str, *, request: Any | None = None) -> Any:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise HTTPException(status_code=400, detail="file_id is required")

        owner_id = _resolve_file_asset_owner_id(request)
        try:
            record, file_path = resolve_file_for_owner(normalized_file_id, owner_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        target = Path(file_path).resolve()
        media_type = str(record.get("mime_type") or "application/octet-stream")
        if str(request_method or "").upper() == "HEAD":
            return Response(
                status_code=200,
                headers={
                    "Content-Length": str(target.stat().st_size),
                    "Content-Type": media_type,
                },
            )
        return FileResponse(
            path=str(target),
            media_type=media_type,
            filename=str(record.get("filename") or target.name),
            content_disposition_type="inline",
        )

    def _build_health_payload() -> Dict[str, str]:
        return health_runtime.build_payload(
            python_executable=python_executable,
            python_prefix=python_prefix,
            python_base_prefix=python_base_prefix,
            python_venv_active=python_venv_active,
            provider_diag=module2_bootstrap_runtime.provider_preflight_snapshot(),
            provider_config=module2_bootstrap_runtime.provider_config_snapshot(
                build_provider=build_preflight_provider,
            ),
            mineru_warmup=module2_bootstrap_runtime.mineru_warmup_snapshot(),
            office_preview_jobs_in_memory=office_preview_runtime.job_count(),
            module4_sync_enabled=module4_sync_config_runtime.sync_enabled(),
            module4_sync_inflight_batches=module4_sync_task_runtime.inflight_batch_count(),
            module4_sync_inflight_outbox=module4_sync_task_runtime.inflight_outbox_count(),
            module4_sync_metrics=module4_sync_metrics_runtime.snapshot(),
            storage_diag=resolved_runtime_state_repository.diagnostics(),
        )

    async def _startup() -> None:
        await app_lifecycle_runtime.startup(
            connect_storage=resolved_runtime_state_repository.connect,
            recover_module4_sync_outbox=_recover_module4_sync_outbox,
            recover_extraction_jobs=_recover_extraction_jobs,
            provider_preflight_on_startup=module2_bootstrap_runtime.provider_preflight_on_startup(),
            startup_provider_preflight_task=lambda: module2_bootstrap_runtime.startup_provider_preflight_task(
                build_provider=build_preflight_provider,
            ),
            startup_mineru_warmup_task=lambda: module2_bootstrap_runtime.startup_mineru_warmup_task(
                run_parse_in_process_pool=run_parse_in_process_pool,
            ),
            track_startup_task=startup_task_runtime.track,
        )

    async def _shutdown() -> None:
        await app_lifecycle_runtime.shutdown(
            shutdown_startup_tasks=startup_task_runtime.shutdown,
            shutdown_extraction_job_runtime=lambda: extraction_job_runtime.shutdown_runtime(
                persist_snapshot=extraction_job_runtime.persist_snapshot
            ),
            shutdown_module4_sync_tasks=lambda: module4_sync_task_runtime.shutdown(
                drain_timeout=module4_sync_config_runtime.shutdown_drain_sec()
            ),
            close_storage=resolved_runtime_state_repository.close,
            shutdown_process_pool=shutdown_process_pool,
        )

    return Module2AppCallbackBundle(
        clear_cache_request=_clear_cache_request,
        serve_layout_preview=_serve_layout_preview,
        serve_artifact=_serve_artifact,
        serve_file_asset=_serve_file_asset,
        build_health_payload=_build_health_payload,
        startup=_startup,
        shutdown=_shutdown,
    )
