from __future__ import annotations

"""App entry bundle builders for module2 extraction service layer."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ...composition.app_callback_bundle import Module2AppCallbackBundle, build_module2_app_callback_bundle
from ...api.v1.router_bundle import build_module2_api_routers


@dataclass(frozen=True)
class Module2MainEntryBundle:
    module2_app_callback_bundle: Module2AppCallbackBundle
    routers: tuple[Any, ...]

    def lifespan(self):
        @asynccontextmanager
        async def _lifespan(app: Any):
            await self.module2_app_callback_bundle.startup()
            try:
                yield
            finally:
                await self.module2_app_callback_bundle.shutdown()

        return _lifespan

    def register_app(self, app: Any) -> None:
        for router in self.routers:
            app.include_router(router)


def build_module2_main_entry_bundle(
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
    extraction_jobs,
    extraction_lock,
    extraction_job_runtime_specs,
    extraction_job_tasks,
    extraction_job_persist_markers,
    clear_mineru_process_runtime_cache,
    reset_process_pool,
    build_preflight_provider,
    run_parse_in_process_pool,
    schedule_module4_sync_outbox,
    shutdown_process_pool,
    python_executable: str,
    python_prefix: str,
    python_base_prefix: str,
    python_venv_active: bool,
    extraction_request_runtime,
    office_preview_request_runtime,
    document_tools_runtime,
    assistant1_runtime,
    list_outbox_rows,
    get_outbox_row,
    build_list_response,
    serialize_outbox_row,
    metrics_snapshot,
) -> Module2MainEntryBundle:
    if runtime_state_repository is None:
        raise ValueError("runtime_state_repository is required")
    module2_app_callback_bundle = build_module2_app_callback_bundle(
        app_lifecycle_runtime=app_lifecycle_runtime,
        cache_clear_runtime=cache_clear_runtime,
        artifact_file_runtime=artifact_file_runtime,
        health_runtime=health_runtime,
        module2_bootstrap_runtime=module2_bootstrap_runtime,
        startup_task_runtime=startup_task_runtime,
        runtime_state_repository=runtime_state_repository,
        office_preview_runtime=office_preview_runtime,
        module4_sync_config_runtime=module4_sync_config_runtime,
        module4_sync_outbox_runtime=module4_sync_outbox_runtime,
        module4_sync_metrics_runtime=module4_sync_metrics_runtime,
        module4_sync_task_runtime=module4_sync_task_runtime,
        extraction_job_runtime=extraction_job_runtime,
        extraction_jobs=extraction_jobs,
        extraction_lock=extraction_lock,
        extraction_job_runtime_specs=extraction_job_runtime_specs,
        extraction_job_tasks=extraction_job_tasks,
        extraction_job_persist_markers=extraction_job_persist_markers,
        clear_mineru_process_runtime_cache=clear_mineru_process_runtime_cache,
        reset_process_pool=reset_process_pool,
        build_preflight_provider=build_preflight_provider,
        run_parse_in_process_pool=run_parse_in_process_pool,
        schedule_module4_sync_outbox=schedule_module4_sync_outbox,
        shutdown_process_pool=shutdown_process_pool,
        python_executable=python_executable,
        python_prefix=python_prefix,
        python_base_prefix=python_base_prefix,
        python_venv_active=python_venv_active,
    )
    routers = build_module2_api_routers(
        extraction_request_runtime=extraction_request_runtime,
        office_preview_request_runtime=office_preview_request_runtime,
        document_tools_runtime=document_tools_runtime,
        clear_cache_request=module2_app_callback_bundle.clear_cache_request,
        serve_layout_preview=module2_app_callback_bundle.serve_layout_preview,
        serve_artifact=module2_app_callback_bundle.serve_artifact,
        serve_file_asset=module2_app_callback_bundle.serve_file_asset,
        build_health_payload=module2_app_callback_bundle.build_health_payload,
        assistant1_runtime=assistant1_runtime,
        list_outbox_rows=list_outbox_rows,
        get_outbox_row=get_outbox_row,
        build_list_response=build_list_response,
        serialize_outbox_row=serialize_outbox_row,
        metrics_snapshot=metrics_snapshot,
    )
    return Module2MainEntryBundle(
        module2_app_callback_bundle=module2_app_callback_bundle,
        routers=routers,
    )
