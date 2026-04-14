from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_module(module_file: str, module_name: str):
    module_path = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "services" / module_file
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


executor_module = _load_module("extraction_executor_service.py", "_smart_doc_flow_module2_extraction_job_executor_service")
job_runtime_module = _load_module(
    "extraction_job_service.py",
    "_smart_doc_flow_module2_extraction_job_service_for_executor",
)
ExtractionJobExecutor = executor_module.ExtractionJobExecutor
ExtractionJobRuntime = job_runtime_module.ExtractionJobRuntime


@dataclass
class FakeFileState:
    file_name: str
    file_hash: str
    status: str
    stage: str
    progress_ratio: float
    message: str
    artifact_path: str | None = None
    artifact_url: str | None = None
    error: str = ""
    track: str = ""
    cached: bool = False


@dataclass
class FakeDocument:
    file_name: str
    file_hash: str
    errors: list[str]
    track: str = "VisualTrack"
    cached: bool = False

    def model_dump(self, mode: str = "json") -> dict:
        del mode
        return {
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "errors": list(self.errors),
            "track": self.track,
            "cached": self.cached,
        }


@dataclass
class FakeJob:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    total_files: int
    completed_files: int
    failed_files: int
    current_file_index: int
    current_file_name: str
    current_stage: str
    files: list[FakeFileState]
    documents: list[FakeDocument]
    errors: list[str]

    def terminal(self) -> bool:
        return self.status in {"completed", "failed"}


def _build_job_runtime(tmp_path: Path, persist_calls: list[tuple[str, bool]]):
    state_root = tmp_path / "state"
    artifact_root = tmp_path / "artifacts"
    state_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)

    runtime = ExtractionJobRuntime(
        state_root_factory=lambda: state_root,
        safe_artifact_path=lambda path_fragment: artifact_root / str(path_fragment or "").strip().strip("/"),
        job_state_factory=FakeJob,
        job_file_state_factory=FakeFileState,
        document_validate=lambda item: FakeDocument(
            file_name=str(item.get("file_name") or ""),
            file_hash=str(item.get("file_hash") or ""),
            errors=list(item.get("errors") or []),
            track=str(item.get("track") or "VisualTrack"),
            cached=bool(item.get("cached", False)),
        ),
        run_extraction_job=lambda **kwargs: asyncio.sleep(0),
        logger=logging.getLogger("test-executor-runtime"),
    )

    original_persist_snapshot = runtime.persist_snapshot

    async def _tracked_persist_snapshot(job_id: str, force: bool) -> None:
        persist_calls.append((job_id, force))
        await original_persist_snapshot(job_id, force)

    runtime.persist_snapshot = _tracked_persist_snapshot  # type: ignore[method-assign]
    return runtime


def _seed_job(runtime: Any, job_id: str = "job-1") -> FakeJob:
    loaded_files = [
        (
            "demo.pdf",
            b"%PDF",
            "hash-1",
            "uploaded/demo.pdf",
            "/extract/artifact/uploaded/demo.pdf",
            "application/pdf",
        )
    ]
    job = runtime.build_queued_job_state(job_id=job_id, loaded_files=loaded_files)
    runtime.jobs[job_id] = job
    return job


class _FakeModule4SyncCallbackBundle:
    def __init__(self, *, enqueue_for_seed) -> None:
        self._enqueue_for_seed = enqueue_for_seed

    async def enqueue_document_sync_for_seed(self, **kwargs) -> bool:
        return await self._enqueue_for_seed(**kwargs)


def test_extraction_job_executor_run_file_task_success(tmp_path: Path) -> None:
    persist_calls: list[tuple[str, bool]] = []
    sync_calls: list[dict] = []
    runtime = _build_job_runtime(tmp_path, persist_calls)
    _seed_job(runtime)

    async def _process_single_doc_bytes(**kwargs):
        progress_hook = kwargs["progress_hook"]
        await progress_hook("parsing", 0.5, "running", {})
        return FakeDocument(file_name="demo.pdf", file_hash="hash-1", errors=[])

    async def _enqueue_module4_document_sync(**kwargs) -> None:
        sync_calls.append(dict(kwargs))

    async def _enqueue_document_sync_for_seed(**kwargs) -> bool:
        sync_calls.append(dict(kwargs))
        return True

    executor = ExtractionJobExecutor(
        extraction_job_runtime=runtime,
        module4_sync_callback_bundle=_FakeModule4SyncCallbackBundle(
            enqueue_for_seed=_enqueue_document_sync_for_seed
        ),
        file_semaphore=asyncio.Semaphore(1),
        process_single_doc_bytes=_process_single_doc_bytes,
        logger=logging.getLogger("test-executor"),
    )

    async def _scenario() -> None:
        await executor.run_file_task(
            job_id="job-1",
            file_index=1,
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            file_hash="hash-1",
            schema_obj={},
            schema_digest="schema-1",
            max_retries=1,
            tenant_id="tenant-a",
        )

    asyncio.run(_scenario())

    job = runtime.jobs["job-1"]
    assert job.completed_files == 1
    assert job.failed_files == 0
    assert job.files[0].status == "completed"
    assert job.files[0].track == "VisualTrack"
    assert job.documents and job.documents[0].file_name == "demo.pdf"
    assert any(force is False for _, force in persist_calls)
    assert any(force is True for _, force in persist_calls)
    assert sync_calls and sync_calls[0]["tenant_id"] == "tenant-a"
    assert sync_calls[0]["mode"] == "per_file"


def test_extraction_job_executor_run_job_finalizes_and_syncs_batch(tmp_path: Path) -> None:
    persist_calls: list[tuple[str, bool]] = []
    final_sync_calls: list[dict] = []
    runtime = _build_job_runtime(tmp_path, persist_calls)
    _seed_job(runtime)

    async def _process_single_doc_bytes(**kwargs):
        return FakeDocument(file_name="demo.pdf", file_hash="hash-1", errors=[])

    async def _enqueue_document_sync_for_seed(**kwargs) -> bool:
        final_sync_calls.append(dict(kwargs))
        return kwargs.get("mode") == "final_batch"

    executor = ExtractionJobExecutor(
        extraction_job_runtime=runtime,
        module4_sync_callback_bundle=_FakeModule4SyncCallbackBundle(
            enqueue_for_seed=_enqueue_document_sync_for_seed
        ),
        file_semaphore=asyncio.Semaphore(1),
        process_single_doc_bytes=_process_single_doc_bytes,
        logger=logging.getLogger("test-executor"),
    )

    async def _scenario() -> None:
        await executor.run_job(
            job_id="job-1",
            loaded_files=[("demo.pdf", b"%PDF", "hash-1", "artifact", "url", "application/pdf")],
            schema_obj={},
            schema_digest="schema-1",
            max_retries=1,
            tenant_id="tenant-a",
        )

    asyncio.run(_scenario())

    job = runtime.jobs["job-1"]
    assert job.status == "completed"
    assert job.current_stage == "completed"
    assert job.documents and job.documents[0].file_hash == "hash-1"
    assert [call["mode"] for call in final_sync_calls] == ["per_file", "final_batch"]
    assert any(force is True for _, force in persist_calls)
