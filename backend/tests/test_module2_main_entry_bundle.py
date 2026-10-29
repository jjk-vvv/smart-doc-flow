from __future__ import annotations

import asyncio
import logging
import sys
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_entry_bundle_module = import_module("app.modules.module2.bootstrap.entry")


class _StorageStub:
    async def clear_runtime_cache(self):
        return {}

    def diagnostics(self):
        return {}

    async def connect(self):
        return None

    async def close(self):
        return None

    async def list_graph_sync_outbox(self, **kwargs):
        return []

    async def get_graph_sync_outbox(self, outbox_id: str):
        return None


class _Module4SyncConfigStub:
    def sync_enabled(self) -> bool:
        return True

    def shutdown_drain_sec(self) -> float:
        return 0.1


class _Module2BootstrapRuntimeStub:
    def provider_preflight_snapshot(self):
        return {}

    def provider_config_snapshot(self, *, build_provider):
        return {}

    def mineru_warmup_snapshot(self):
        return {}

    def provider_preflight_on_startup(self):
        return False

    async def startup_provider_preflight_task(self, *, build_provider):
        return None

    async def startup_mineru_warmup_task(self, *, run_parse_in_process_pool):
        return None


class _OfficePreviewRuntimeStub:
    async def clear(self):
        return None

    def job_count(self) -> int:
        return 0


class _Module4SyncTaskRuntimeStub:
    def tasks_view(self):
        return set()

    def index_view(self):
        return {}

    def inflight_batch_count(self) -> int:
        return 0

    def inflight_outbox_count(self) -> int:
        return 0

    async def shutdown(self, *, drain_timeout: float):
        return None


class _Module4SyncMetricsRuntimeStub:
    def snapshot(self):
        return {}


class _ExtractionJobRuntimeStub:
    async def recover_from_snapshots(self):
        return None

    async def shutdown_runtime(self, *, persist_snapshot):
        return None

    async def persist_snapshot(self):
        return None


class _StartupTaskRuntimeStub:
    def track(self, task):
        return task

    async def shutdown(self):
        return None


class _AppLifecycleRuntimeStub:
    def __init__(self) -> None:
        self.startup_calls = 0
        self.shutdown_calls = 0

    async def startup(self, **kwargs):
        self.startup_calls += 1
        return None

    async def shutdown(self, **kwargs):
        self.shutdown_calls += 1
        return None


class _RuntimeStub:
    async def create_job(self, **kwargs):
        return {}

    async def get_job_status(self, job_id, include_documents=False):
        return {}

    async def extract_batch(self, **kwargs):
        return {}

    async def start(self, file):
        return {}

    async def get_status(self, job_id):
        return {}

    def summarize(self, payload):
        return {}

    def trace_locate(self, payload):
        return {}

    def stream_chat(self, **kwargs):
        async def _empty():
            if False:
                yield b""

        return _empty()


def test_build_module2_main_entry_bundle_exposes_callback_bundle_and_routers() -> None:
    _logger = logging.getLogger("test.module2.main_entry_bundle")
    storage = _StorageStub()
    runtime_stub = _RuntimeStub()
    app_lifecycle_runtime = _AppLifecycleRuntimeStub()

    bundle = main_entry_bundle_module.build_module2_main_entry_bundle(
        app_lifecycle_runtime=app_lifecycle_runtime,
        cache_clear_runtime=object(),
        artifact_file_runtime=object(),
        health_runtime=object(),
        module2_bootstrap_runtime=_Module2BootstrapRuntimeStub(),
        startup_task_runtime=_StartupTaskRuntimeStub(),
        runtime_state_repository=storage,
        office_preview_runtime=_OfficePreviewRuntimeStub(),
        module4_sync_config_runtime=_Module4SyncConfigStub(),
        module4_sync_outbox_runtime=object(),
        module4_sync_metrics_runtime=_Module4SyncMetricsRuntimeStub(),
        module4_sync_task_runtime=_Module4SyncTaskRuntimeStub(),
        extraction_job_runtime=_ExtractionJobRuntimeStub(),
        extraction_jobs={},
        extraction_lock=asyncio.Lock(),
        extraction_job_runtime_specs={},
        extraction_job_tasks={},
        extraction_job_persist_markers={},
        clear_mineru_process_runtime_cache=lambda: None,
        reset_process_pool=lambda reason: 0,
        build_preflight_provider=lambda: object(),
        run_parse_in_process_pool=lambda **kwargs: None,
        schedule_module4_sync_outbox=lambda outbox_id: None,
        shutdown_process_pool=lambda: None,
        python_executable="python",
        python_prefix="prefix",
        python_base_prefix="base_prefix",
        python_venv_active=True,
        extraction_request_runtime=runtime_stub,
        office_preview_request_runtime=runtime_stub,
        document_tools_runtime=runtime_stub,
        assistant1_runtime=runtime_stub,
        list_outbox_rows=storage.list_graph_sync_outbox,
        get_outbox_row=storage.get_graph_sync_outbox,
        build_list_response=lambda **kwargs: kwargs,
        serialize_outbox_row=lambda row, include_payload=False: row,
        metrics_snapshot=lambda: {},
    )

    assert bundle.module2_app_callback_bundle is not None
    assert len(bundle.routers) == 4

    app = FastAPI()
    bundle.register_app(app)

    async def _exercise_lifespan() -> None:
        async with bundle.lifespan()(app):
            pass

    asyncio.run(_exercise_lifespan())

    assert app_lifecycle_runtime.startup_calls == 1
    assert app_lifecycle_runtime.shutdown_calls == 1
    assert len(app.router.on_startup) == 0
    assert len(app.router.on_shutdown) == 0
    assert len(app.routes) >= 4
