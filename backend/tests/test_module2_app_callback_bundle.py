from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import FileResponse

from app.modules.module2.runtime.app_callback_bundle import build_module2_app_callback_bundle


class _FakeArtifactFileRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def serve_artifact(
        self,
        *,
        path_fragment: str,
        request_method: str,
        not_found_detail: str,
        default_media_type: str,
    ) -> dict[str, str]:
        payload = {
            "path_fragment": path_fragment,
            "request_method": request_method,
            "not_found_detail": not_found_detail,
            "default_media_type": default_media_type,
        }
        self.calls.append(payload)
        return payload


class _FakeCacheClearRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def clear_request(self, **kwargs):
        self.calls.append(dict(kwargs))
        await kwargs["clear_office_preview_runtime"]()
        scope = str(kwargs["scope"])
        if scope in {"results", "all"}:
            await kwargs["clear_runtime_cache"]()
        if scope in {"runtime", "all"}:
            kwargs["clear_mineru_process_runtime_cache"]()
            kwargs["reset_process_pool"](f"cache_clear:{scope}")
        return {"ok": True, "scope": kwargs["scope"]}


class _FakeHealthRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_payload(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"status": "ok", "llm_provider_model": "gpt-5-mini"}


class _FakeBootstrapRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def provider_preflight_snapshot(self):
        return {"ok": True, "model": "gpt-5-mini"}

    def provider_config_snapshot(self, *, build_provider):
        provider = build_provider()
        return {"configured": True, "provider_type": provider["provider_type"]}

    def mineru_warmup_snapshot(self):
        return {"enabled": True, "status": "completed"}

    def provider_preflight_on_startup(self):
        return True

    async def startup_provider_preflight_task(self, *, build_provider):
        provider = build_provider()
        self._events.append(f"provider:{provider['provider_type']}")

    async def startup_mineru_warmup_task(self, *, run_parse_in_process_pool):
        await run_parse_in_process_pool(context_label="warmup")
        self._events.append("mineru")


class _FakeStartupTaskRuntime:
    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[object]] = []
        self.shutdown_calls = 0

    def track(self, task: asyncio.Task[object]) -> None:
        self.tasks.append(task)

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


class _FakeStorage:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.clear_runtime_cache_calls = 0
        self.close_calls = 0

    async def connect(self) -> None:
        self._events.append("connect_storage")

    async def close(self) -> None:
        self.close_calls += 1
        self._events.append("close_storage")

    async def clear_runtime_cache(self):
        self.clear_runtime_cache_calls += 1
        return {"results": 3}

    def diagnostics(self):
        return {"db_connected": True}


class _FakeOfficePreviewRuntime:
    def __init__(self) -> None:
        self.clear_calls = 0

    async def clear(self) -> None:
        self.clear_calls += 1

    def job_count(self) -> int:
        return 4


class _FakeModule4SyncConfigRuntime:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def sync_enabled(self) -> bool:
        return self.enabled

    def shutdown_drain_sec(self) -> float:
        return 1.5


class _FakeModule4SyncOutboxRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def recover_pending_outbox(self, *, schedule_outbox, limit: int) -> None:
        schedule_outbox("outbox-1")
        self._events.append(f"recover_outbox:{limit}")


class _FakeModule4SyncMetricsRuntime:
    def snapshot(self):
        return {"attempted_batches": 2}


class _FakeModule4SyncTaskRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self._tasks: set[asyncio.Task] = set()
        self._index: dict[str, asyncio.Task] = {}
        self.shutdown_calls: list[float] = []

    def tasks_view(self):
        return self._tasks

    def index_view(self):
        return self._index

    def inflight_batch_count(self) -> int:
        return 5

    def inflight_outbox_count(self) -> int:
        return 6

    async def shutdown(self, *, drain_timeout: float) -> None:
        self.shutdown_calls.append(drain_timeout)
        self._events.append(f"shutdown_module4:{drain_timeout}")


class _FakeExtractionJobRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.jobs = {"job-1": {"status": "running"}}
        self.lock = asyncio.Lock()
        self.runtime_specs = {"job-1": {"schema": {}}}
        self.tasks: dict[str, asyncio.Task] = {}
        self.persist_markers = {"job-1": 1.0}
        self.recover_calls = 0
        self.shutdown_calls = 0

    async def recover_from_snapshots(self) -> None:
        self.recover_calls += 1
        self._events.append("recover_jobs")

    async def shutdown_runtime(self, *, persist_snapshot) -> None:
        self.shutdown_calls += 1
        await persist_snapshot("job-1", True)
        self._events.append("shutdown_jobs")

    async def persist_snapshot(self, job_id: str, force: bool = False) -> None:
        self._events.append(f"persist:{job_id}:{force}")


class _FakeAppLifecycleRuntime:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def startup(self, **kwargs) -> None:
        await kwargs["connect_storage"]()
        await kwargs["recover_module4_sync_outbox"]()
        await kwargs["recover_extraction_jobs"]()
        assert kwargs["provider_preflight_on_startup"] is True
        await kwargs["startup_provider_preflight_task"]()
        await kwargs["startup_mineru_warmup_task"]()
        self._events.append("startup_complete")

    async def shutdown(self, **kwargs) -> None:
        await kwargs["shutdown_startup_tasks"]()
        await kwargs["shutdown_extraction_job_runtime"]()
        await kwargs["shutdown_module4_sync_tasks"]()
        await kwargs["close_storage"]()
        kwargs["shutdown_process_pool"]()
        self._events.append("shutdown_complete")


def test_app_callback_bundle_orchestrates_support_callbacks_and_lifecycle() -> None:
    events: list[str] = []
    artifact_runtime = _FakeArtifactFileRuntime()
    cache_clear_runtime = _FakeCacheClearRuntime()
    health_runtime = _FakeHealthRuntime()
    bootstrap_runtime = _FakeBootstrapRuntime(events)
    startup_task_runtime = _FakeStartupTaskRuntime()
    storage = _FakeStorage(events)
    office_preview_runtime = _FakeOfficePreviewRuntime()
    module4_sync_config_runtime = _FakeModule4SyncConfigRuntime(enabled=True)
    module4_sync_outbox_runtime = _FakeModule4SyncOutboxRuntime(events)
    module4_sync_metrics_runtime = _FakeModule4SyncMetricsRuntime()
    module4_sync_task_runtime = _FakeModule4SyncTaskRuntime(events)
    extraction_job_runtime = _FakeExtractionJobRuntime(events)
    app_lifecycle_runtime = _FakeAppLifecycleRuntime(events)
    process_pool_reasons: list[str] = []
    scheduled_outbox: list[str] = []

    async def _run_parse_in_process_pool(**kwargs):
        events.append(f"warmup:{kwargs['context_label']}")
        return None

    def _reset_process_pool(reason: str) -> int:
        process_pool_reasons.append(reason)
        return 11

    def _schedule_module4_sync_outbox(payload) -> None:
        scheduled_outbox.append(str(payload))

    def _shutdown_process_pool() -> None:
        events.append("shutdown_process_pool")

    def _build_preflight_provider():
        return {"provider_type": "openai_compatible"}

    bundle = build_module2_app_callback_bundle(
        app_lifecycle_runtime=app_lifecycle_runtime,
        cache_clear_runtime=cache_clear_runtime,
        artifact_file_runtime=artifact_runtime,
        health_runtime=health_runtime,
        module2_bootstrap_runtime=bootstrap_runtime,
        startup_task_runtime=startup_task_runtime,
        runtime_state_repository=storage,
        office_preview_runtime=office_preview_runtime,
        module4_sync_config_runtime=module4_sync_config_runtime,
        module4_sync_outbox_runtime=module4_sync_outbox_runtime,
        module4_sync_metrics_runtime=module4_sync_metrics_runtime,
        module4_sync_task_runtime=module4_sync_task_runtime,
        extraction_job_runtime=extraction_job_runtime,
        extraction_jobs=extraction_job_runtime.jobs,
        extraction_lock=extraction_job_runtime.lock,
        extraction_job_runtime_specs=extraction_job_runtime.runtime_specs,
        extraction_job_tasks=extraction_job_runtime.tasks,
        extraction_job_persist_markers=extraction_job_runtime.persist_markers,
        clear_mineru_process_runtime_cache=lambda: events.append("clear_mineru_runtime"),
        reset_process_pool=_reset_process_pool,
        build_preflight_provider=_build_preflight_provider,
        run_parse_in_process_pool=_run_parse_in_process_pool,
        schedule_module4_sync_outbox=_schedule_module4_sync_outbox,
        shutdown_process_pool=_shutdown_process_pool,
        python_executable="python.exe",
        python_prefix="/venv",
        python_base_prefix="/python",
        python_venv_active=True,
    )

    async def _scenario() -> None:
        health_payload = bundle.build_health_payload()
        assert health_payload["status"] == "ok"
        clear_payload = await bundle.clear_cache_request("runtime")
        assert clear_payload == {"ok": True, "scope": "runtime"}
        layout_payload = bundle.serve_layout_preview("demo.pdf", "GET")
        artifact_payload = bundle.serve_artifact("preview/uploaded/demo.pdf", "HEAD")
        assert layout_payload["path_fragment"] == "layout/demo.pdf"
        assert artifact_payload["path_fragment"] == "preview/uploaded/demo.pdf"
        await bundle.startup()
        await bundle.shutdown()

    asyncio.run(_scenario())

    assert scheduled_outbox == ["outbox-1"]
    assert cache_clear_runtime.calls and cache_clear_runtime.calls[0]["scope"] == "runtime"
    assert cache_clear_runtime.calls[0]["extraction_jobs"] is extraction_job_runtime.jobs
    assert process_pool_reasons == ["cache_clear:runtime"]
    assert health_runtime.calls and health_runtime.calls[0]["python_executable"] == "python.exe"
    assert health_runtime.calls[0]["office_preview_jobs_in_memory"] == 4
    assert artifact_runtime.calls[0]["default_media_type"] == "application/pdf"
    assert artifact_runtime.calls[1]["default_media_type"] == "application/octet-stream"
    assert extraction_job_runtime.recover_calls == 1
    assert extraction_job_runtime.shutdown_calls == 1
    assert storage.clear_runtime_cache_calls == 0
    assert storage.close_calls == 1
    assert office_preview_runtime.clear_calls == 1
    assert module4_sync_task_runtime.shutdown_calls == [1.5]
    assert startup_task_runtime.shutdown_calls == 1
    assert events == [
        "clear_mineru_runtime",
        "connect_storage",
        "recover_outbox:200",
        "recover_jobs",
        "provider:openai_compatible",
        "warmup:warmup",
        "mineru",
        "startup_complete",
        "persist:job-1:True",
        "shutdown_jobs",
        "shutdown_module4:1.5",
        "close_storage",
        "shutdown_process_pool",
        "shutdown_complete",
    ]


def test_app_callback_bundle_skips_outbox_recovery_when_sync_disabled() -> None:
    events: list[str] = []
    app_lifecycle_runtime = _FakeAppLifecycleRuntime(events)
    module4_sync_config_runtime = _FakeModule4SyncConfigRuntime(enabled=False)

    bundle = build_module2_app_callback_bundle(
        app_lifecycle_runtime=app_lifecycle_runtime,
        cache_clear_runtime=_FakeCacheClearRuntime(),
        artifact_file_runtime=_FakeArtifactFileRuntime(),
        health_runtime=_FakeHealthRuntime(),
        module2_bootstrap_runtime=_FakeBootstrapRuntime(events),
        startup_task_runtime=_FakeStartupTaskRuntime(),
        runtime_state_repository=_FakeStorage(events),
        office_preview_runtime=_FakeOfficePreviewRuntime(),
        module4_sync_config_runtime=module4_sync_config_runtime,
        module4_sync_outbox_runtime=_FakeModule4SyncOutboxRuntime(events),
        module4_sync_metrics_runtime=_FakeModule4SyncMetricsRuntime(),
        module4_sync_task_runtime=_FakeModule4SyncTaskRuntime(events),
        extraction_job_runtime=_FakeExtractionJobRuntime(events),
        extraction_jobs={},
        extraction_lock=asyncio.Lock(),
        extraction_job_runtime_specs={},
        extraction_job_tasks={},
        extraction_job_persist_markers={},
        clear_mineru_process_runtime_cache=lambda: None,
        reset_process_pool=lambda reason: 0,
        build_preflight_provider=lambda: {"provider_type": "openai_compatible"},
        run_parse_in_process_pool=lambda **kwargs: asyncio.sleep(0),
        schedule_module4_sync_outbox=lambda payload: events.append(f"scheduled:{payload}"),
        shutdown_process_pool=lambda: None,
        python_executable="python.exe",
        python_prefix="/venv",
        python_base_prefix="/python",
        python_venv_active=True,
    )

    async def _scenario() -> None:
        await bundle.startup()

    asyncio.run(_scenario())

    assert "recover_outbox:200" not in events
    assert not any(item.startswith("scheduled:") for item in events)


def test_app_callback_bundle_serves_file_asset_with_default_owner(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []
    source_file = (tmp_path / "file-assets" / "asset.txt").resolve()
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("file asset body", encoding="utf-8")

    monkeypatch.setattr(
        "app.modules.module2.composition.app_callback_bundle.resolve_file_for_owner",
        lambda file_id, owner_id: (
            {
                "file_id": file_id,
                "filename": "asset.txt",
                "mime_type": "text/plain",
            },
            source_file,
        ),
    )

    bundle = build_module2_app_callback_bundle(
        app_lifecycle_runtime=_FakeAppLifecycleRuntime(events),
        cache_clear_runtime=_FakeCacheClearRuntime(),
        artifact_file_runtime=_FakeArtifactFileRuntime(),
        health_runtime=_FakeHealthRuntime(),
        module2_bootstrap_runtime=_FakeBootstrapRuntime(events),
        startup_task_runtime=_FakeStartupTaskRuntime(),
        runtime_state_repository=_FakeStorage(events),
        office_preview_runtime=_FakeOfficePreviewRuntime(),
        module4_sync_config_runtime=_FakeModule4SyncConfigRuntime(enabled=False),
        module4_sync_outbox_runtime=_FakeModule4SyncOutboxRuntime(events),
        module4_sync_metrics_runtime=_FakeModule4SyncMetricsRuntime(),
        module4_sync_task_runtime=_FakeModule4SyncTaskRuntime(events),
        extraction_job_runtime=_FakeExtractionJobRuntime(events),
        extraction_jobs={},
        extraction_lock=asyncio.Lock(),
        extraction_job_runtime_specs={},
        extraction_job_tasks={},
        extraction_job_persist_markers={},
        clear_mineru_process_runtime_cache=lambda: None,
        reset_process_pool=lambda reason: 0,
        build_preflight_provider=lambda: {"provider_type": "openai_compatible"},
        run_parse_in_process_pool=lambda **kwargs: asyncio.sleep(0),
        schedule_module4_sync_outbox=lambda payload: None,
        shutdown_process_pool=lambda: None,
        python_executable="python.exe",
        python_prefix="/venv",
        python_base_prefix="/python",
        python_venv_active=True,
    )

    head_response = bundle.serve_file_asset("fa_asset", "HEAD")
    get_response = bundle.serve_file_asset("fa_asset", "GET")

    assert head_response.status_code == 200
    assert head_response.headers.get("content-type", "").startswith("text/plain")
    assert head_response.headers.get("content-length") == str(source_file.stat().st_size)
    assert isinstance(get_response, FileResponse)
    assert get_response.status_code == 200


def test_app_callback_bundle_serve_file_asset_prefers_request_owner(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []
    source_file = (tmp_path / "file-assets" / "owner.txt").resolve()
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("owner body", encoding="utf-8")

    captured_owner: dict[str, str] = {}

    def _resolve(file_id: str, owner_id: str):
        captured_owner["file_id"] = file_id
        captured_owner["owner_id"] = owner_id
        return (
            {
                "file_id": file_id,
                "filename": "owner.txt",
                "mime_type": "text/plain",
            },
            source_file,
        )

    monkeypatch.setattr(
        "app.modules.module2.composition.app_callback_bundle.resolve_file_for_owner",
        _resolve,
    )

    bundle = build_module2_app_callback_bundle(
        app_lifecycle_runtime=_FakeAppLifecycleRuntime(events),
        cache_clear_runtime=_FakeCacheClearRuntime(),
        artifact_file_runtime=_FakeArtifactFileRuntime(),
        health_runtime=_FakeHealthRuntime(),
        module2_bootstrap_runtime=_FakeBootstrapRuntime(events),
        startup_task_runtime=_FakeStartupTaskRuntime(),
        runtime_state_repository=_FakeStorage(events),
        office_preview_runtime=_FakeOfficePreviewRuntime(),
        module4_sync_config_runtime=_FakeModule4SyncConfigRuntime(enabled=False),
        module4_sync_outbox_runtime=_FakeModule4SyncOutboxRuntime(events),
        module4_sync_metrics_runtime=_FakeModule4SyncMetricsRuntime(),
        module4_sync_task_runtime=_FakeModule4SyncTaskRuntime(events),
        extraction_job_runtime=_FakeExtractionJobRuntime(events),
        extraction_jobs={},
        extraction_lock=asyncio.Lock(),
        extraction_job_runtime_specs={},
        extraction_job_tasks={},
        extraction_job_persist_markers={},
        clear_mineru_process_runtime_cache=lambda: None,
        reset_process_pool=lambda reason: 0,
        build_preflight_provider=lambda: {"provider_type": "openai_compatible"},
        run_parse_in_process_pool=lambda **kwargs: asyncio.sleep(0),
        schedule_module4_sync_outbox=lambda payload: None,
        shutdown_process_pool=lambda: None,
        python_executable="python.exe",
        python_prefix="/venv",
        python_base_prefix="/python",
        python_venv_active=True,
    )

    request = SimpleNamespace(
        headers={"X-Authenticated-Tenant-Id": "tenant-from-header"},
        state=SimpleNamespace(authenticated_user=SimpleNamespace(tenant_id="tenant-from-state", user_id="user-1")),
    )
    response = bundle.serve_file_asset("fa_owner", "GET", request=request)

    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert captured_owner == {"file_id": "fa_owner", "owner_id": "tenant-from-state"}
