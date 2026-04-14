from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "runtime"
        / "cache_clear.py"
    )
    module_name = "_smart_doc_flow_module2_cache_clear_runtime"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


cache_clear_module = _load_module()
Module2CacheClearRuntime = cache_clear_module.Module2CacheClearRuntime


def test_cache_clear_runtime_preserves_runtime_models_during_results_clear(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MODULE2_MINERU_RUNTIME_MODELS_DIR", raising=False)
    module2_root = tmp_path / "backend" / "module2"
    artifact_root = tmp_path / "artifacts"
    job_state_root = tmp_path / "job_state"
    runtime = Module2CacheClearRuntime(
        module2_root=module2_root,
        artifact_root_factory=lambda: artifact_root,
        resolve_module2_path=lambda raw, default: Path(raw).resolve() if raw else default.resolve(),
        extraction_job_state_root_factory=lambda: job_state_root,
    )

    artifact_root.mkdir(parents=True, exist_ok=True)
    (artifact_root / "layout" / "preview.html").parent.mkdir(parents=True, exist_ok=True)
    (artifact_root / "layout" / "preview.html").write_text("preview", encoding="utf-8")
    runtime_models_dir = artifact_root / "pdf_parse" / "mineru_runtime_models"
    runtime_models_dir.mkdir(parents=True, exist_ok=True)
    (runtime_models_dir / "model.bin").write_bytes(b"model")
    (module2_root / ".mcache").mkdir(parents=True, exist_ok=True)
    (module2_root / ".mcache" / "work.tmp").write_text("tmp", encoding="utf-8")
    job_state_root.mkdir(parents=True, exist_ok=True)
    (job_state_root / "job.json").write_text("{}", encoding="utf-8")

    counts = runtime.clear_materialized_dirs(scope="results")

    assert counts["removed_artifacts"] >= 1
    assert counts["removed_workdirs"] >= 1
    assert counts["removed_job_state"] >= 1
    assert not (artifact_root / "layout" / "preview.html").exists()
    assert (runtime_models_dir / "model.bin").exists()
    assert not (module2_root / ".mcache" / "work.tmp").exists()
    assert not (job_state_root / "job.json").exists()

    runtime_counts = runtime.clear_materialized_dirs(scope="runtime")
    assert runtime_counts["removed_runtime_models"] >= 1
    assert not (runtime_models_dir / "model.bin").exists()


def test_cache_clear_runtime_cancels_tasks_and_clears_memory_state() -> None:
    runtime = Module2CacheClearRuntime(
        module2_root=Path.cwd(),
        artifact_root_factory=lambda: Path.cwd(),
        resolve_module2_path=lambda raw, default: default,
        extraction_job_state_root_factory=lambda: Path.cwd(),
    )

    async def _scenario() -> None:
        office_preview_cleared = {"called": False}
        extraction_jobs = {"job-1": {"status": "running"}}
        extraction_job_runtime_specs = {"job-1": {"schema": {}}}
        extraction_job_persist_markers = {"job-1": 1.0}
        extraction_lock = asyncio.Lock()
        module4_sync_tasks: set[asyncio.Task] = set()
        module4_sync_task_index: dict[str, asyncio.Task] = {}

        async def _sleep_forever() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

        extraction_task = asyncio.create_task(_sleep_forever())
        extraction_job_tasks = {"job-1": extraction_task}
        sync_task = asyncio.create_task(_sleep_forever())
        module4_sync_tasks.add(sync_task)
        module4_sync_task_index["outbox-1"] = sync_task

        async def _clear_office_preview_runtime() -> None:
            office_preview_cleared["called"] = True

        await runtime.clear_extraction_runtime_state(
            extraction_job_tasks=extraction_job_tasks,
            extraction_lock=extraction_lock,
            extraction_jobs=extraction_jobs,
            extraction_job_runtime_specs=extraction_job_runtime_specs,
            extraction_job_persist_markers=extraction_job_persist_markers,
            clear_office_preview_runtime=_clear_office_preview_runtime,
        )
        await runtime.clear_module4_sync_runtime_state(
            module4_sync_tasks=module4_sync_tasks,
            module4_sync_task_index=module4_sync_task_index,
        )

        assert office_preview_cleared["called"] is True
        assert extraction_jobs == {}
        assert extraction_job_runtime_specs == {}
        assert extraction_job_persist_markers == {}
        assert extraction_job_tasks == {}
        assert extraction_task.cancelled()
        assert module4_sync_tasks == set()
        assert module4_sync_task_index == {}
        assert sync_task.cancelled()

    asyncio.run(_scenario())


def test_cache_clear_runtime_clear_request_orchestrates_runtime_cleanup(tmp_path: Path) -> None:
    runtime = Module2CacheClearRuntime(
        module2_root=tmp_path / "backend" / "module2",
        artifact_root_factory=lambda: tmp_path / "artifacts",
        resolve_module2_path=lambda raw, default: default,
        extraction_job_state_root_factory=lambda: tmp_path / "job_state",
    )

    async def _scenario() -> None:
        office_preview_cleared = {"called": False}
        mineru_runtime_cleared = {"called": 0}
        process_pool_reasons: list[str] = []
        runtime_cache_calls = {"count": 0}

        extraction_jobs = {"job-1": {"status": "running"}}
        extraction_job_runtime_specs = {"job-1": {"schema": {}}}
        extraction_job_persist_markers = {"job-1": 1.0}
        extraction_lock = asyncio.Lock()
        module4_sync_tasks: set[asyncio.Task] = set()
        module4_sync_task_index: dict[str, asyncio.Task] = {}

        async def _sleep_forever() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise

        extraction_task = asyncio.create_task(_sleep_forever())
        extraction_job_tasks = {"job-1": extraction_task}
        sync_task = asyncio.create_task(_sleep_forever())
        module4_sync_tasks.add(sync_task)
        module4_sync_task_index["outbox-1"] = sync_task

        async def _clear_office_preview_runtime() -> None:
            office_preview_cleared["called"] = True

        async def _clear_runtime_cache() -> dict[str, int]:
            runtime_cache_calls["count"] += 1
            return {"results": 5}

        def _clear_mineru_process_runtime_cache() -> None:
            mineru_runtime_cleared["called"] += 1

        def _reset_process_pool(reason: str) -> int:
            process_pool_reasons.append(reason)
            return 7

        payload = await runtime.clear_request(
            scope="all",
            extraction_job_tasks=extraction_job_tasks,
            extraction_lock=extraction_lock,
            extraction_jobs=extraction_jobs,
            extraction_job_runtime_specs=extraction_job_runtime_specs,
            extraction_job_persist_markers=extraction_job_persist_markers,
            clear_office_preview_runtime=_clear_office_preview_runtime,
            module4_sync_tasks=module4_sync_tasks,
            module4_sync_task_index=module4_sync_task_index,
            clear_runtime_cache=_clear_runtime_cache,
            clear_mineru_process_runtime_cache=_clear_mineru_process_runtime_cache,
            reset_process_pool=_reset_process_pool,
        )

        assert payload["ok"] is True
        assert payload["message"] == "模块二缓存已清理，scope=all"
        assert payload["scope"] == "all"
        assert payload["cache_counts"] == {"results": 5}
        assert payload["process_pool_reset_generation"] == 7
        assert office_preview_cleared["called"] is True
        assert runtime_cache_calls["count"] == 1
        assert mineru_runtime_cleared["called"] == 1
        assert process_pool_reasons == ["cache_clear:all"]
        assert extraction_jobs == {}
        assert extraction_job_runtime_specs == {}
        assert extraction_job_persist_markers == {}
        assert extraction_job_tasks == {}
        assert extraction_task.cancelled()
        assert module4_sync_tasks == set()
        assert module4_sync_task_index == {}
        assert sync_task.cancelled()

    asyncio.run(_scenario())
