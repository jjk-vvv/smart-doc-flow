from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "services"
        / "extraction_request_service.py"
    )
    module_name = "_smart_doc_flow_module2_extraction_request_service"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


runtime_module = _load_module()
ExtractionRequestRuntime = runtime_module.ExtractionRequestRuntime


@dataclass
class FakeUpload:
    filename: str
    payload: bytes
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        self._read = False

    async def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        if size is None or size < 0:
            return self.payload
        return self.payload[:size]


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
    track: str
    cached: bool
    result: dict[str, Any]
    errors: list[str]
    diagnostics: dict[str, Any]


@dataclass
class FakeJobState:
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


class FakeExtractionJobRuntime:
    def __init__(
        self,
        *,
        jobs: dict[str, FakeJobState] | None = None,
        lock: asyncio.Lock | None = None,
        runtime_specs: dict[str, dict[str, Any]] | None = None,
        job_state_factory: type[FakeJobState] = FakeJobState,
        job_file_state_factory: type[FakeFileState] = FakeFileState,
        cleanup_jobs_locked=lambda: None,
        persist_snapshot=None,
        schedule_extraction_job_task=None,
        serialize_job=None,
        restore_job_from_snapshot=None,
    ) -> None:
        async def _default_persist_snapshot(_job_id: str, _force: bool) -> None:
            return None

        async def _default_restore_job_from_snapshot(_job_id: str):
            return None

        self.jobs = jobs if jobs is not None else {}
        self.lock = lock or asyncio.Lock()
        self.runtime_specs = runtime_specs if runtime_specs is not None else {}
        self.job_state_factory = job_state_factory
        self.job_file_state_factory = job_file_state_factory
        self.cleanup_jobs_locked = cleanup_jobs_locked
        self._persist_snapshot = persist_snapshot or _default_persist_snapshot
        self._schedule_extraction_job_task = schedule_extraction_job_task or (lambda **kwargs: True)
        self._serialize_job = serialize_job or (
            lambda job, include_documents=False: {
                "job_id": job.job_id,
                "status": job.status,
                "include_documents": include_documents,
            }
        )
        self._restore_job_from_snapshot = restore_job_from_snapshot or _default_restore_job_from_snapshot

    async def register_job(
        self,
        *,
        loaded_files: list[tuple[str, bytes, str, str, str, str]],
        schema_obj: dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> FakeJobState:
        job_id = f"extract_job_fake_{len(self.jobs) + 1}"
        now_ts = time.time()
        job_state = self.job_state_factory(
            job_id=job_id,
            status="queued",
            created_at=now_ts,
            updated_at=now_ts,
            total_files=len(loaded_files),
            completed_files=0,
            failed_files=0,
            current_file_index=0,
            current_file_name="",
            current_stage="queued",
            files=[
                self.job_file_state_factory(
                    file_name=file_name,
                    file_hash=file_hash,
                    status="queued",
                    stage="queued",
                    progress_ratio=0.0,
                    message="queued",
                    artifact_path=artifact_path,
                    artifact_url=artifact_url,
                )
                for file_name, _file_bytes, file_hash, artifact_path, artifact_url, _mime_type in loaded_files
            ],
            documents=[],
            errors=[],
        )
        self.cleanup_jobs_locked()
        self.jobs[job_id] = job_state
        self.runtime_specs[job_id] = {
            "schema": schema_obj,
            "schema_digest": schema_digest,
            "max_retries": max_retries,
            "tenant_id": tenant_id,
            "loaded_files": [
                {
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "artifact_path": artifact_path,
                    "artifact_url": artifact_url,
                    "mime_type": mime_type,
                }
                for file_name, _file_bytes, file_hash, artifact_path, artifact_url, mime_type in loaded_files
            ],
        }
        await self._persist_snapshot(job_id, True)
        self._schedule_extraction_job_task(
            job_id=job_id,
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=tenant_id,
        )
        return job_state

    async def find_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if job is not None:
            return job
        return await self._restore_job_from_snapshot(job_id)

    def serialize_job(self, job: FakeJobState, *, include_documents: bool = False) -> dict[str, Any]:
        return self._serialize_job(job, include_documents=include_documents)


class FakeModule4SyncCallbackBundle:
    def __init__(self, *, enqueue_for_seed=None) -> None:
        async def _default_enqueue_for_seed(**kwargs) -> bool:
            return False

        self._enqueue_for_seed = enqueue_for_seed or _default_enqueue_for_seed

    async def enqueue_document_sync_for_seed(self, **kwargs) -> bool:
        return await self._enqueue_for_seed(**kwargs)


def _build_job_runtime(**overrides):
    return FakeExtractionJobRuntime(**overrides)


def _build_runtime(**overrides):
    async def _process_single_doc_bytes(**kwargs):
        return FakeDocument(
            file_name=kwargs["file_name"],
            file_hash=f"hash-{kwargs['file_name']}",
            track="VisualTrack",
            cached=False,
            result={"ok": True},
            errors=[],
            diagnostics={},
        )

    async def _triage(file_name: str, file_bytes: bytes, schema_digest: str):
        return SimpleNamespace(
            cached_payload=None,
            file_name=file_name,
            file_bytes_len=len(file_bytes),
            schema_digest=schema_digest,
        )

    async def _ensure_provider_ready_for_job_create():
        return None

    async def _persist_snapshot(_job_id: str, _force: bool) -> None:
        return None

    async def _restore_job_from_snapshot(_job_id: str):
        return None

    async def _enqueue_document_sync_for_seed(**kwargs) -> bool:
        return False

    defaults = dict(
        process_single_doc_bytes=_process_single_doc_bytes,
        parse_schema_form_json=lambda raw_schema: {"raw": raw_schema},
        write_artifact_bytes=lambda **kwargs: (
            f"preview/uploaded/{kwargs['file_name']}",
            f"/extract/artifact/preview/uploaded/{kwargs['file_name']}",
        ),
        schema_hash=lambda schema: f"schema:{sorted(schema.keys())}",
        build_stream_router=lambda: SimpleNamespace(triage=_triage),
        ensure_provider_ready_for_job_create=_ensure_provider_ready_for_job_create,
        module4_tenant=lambda request, explicit="": explicit or "default",
        extraction_job_runtime=_build_job_runtime(
            persist_snapshot=_persist_snapshot,
            restore_job_from_snapshot=_restore_job_from_snapshot,
        ),
        module4_sync_callback_bundle=FakeModule4SyncCallbackBundle(
            enqueue_for_seed=_enqueue_document_sync_for_seed
        ),
        extraction_result_factory=lambda payload: payload,
        document_response_factory=FakeDocument,
        batch_response_factory=lambda documents: SimpleNamespace(documents=documents),
        logger=logging.getLogger("test-extraction-request-runtime"),
    )
    defaults.update(overrides)
    return ExtractionRequestRuntime(**defaults)


def test_extraction_request_runtime_create_job_schedules_and_persists(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_MAX_RETRIES", "3")

    provider_ready_calls: list[str] = []
    persist_calls: list[tuple[str, bool]] = []
    schedule_calls: list[dict[str, Any]] = []
    cleanup_calls: list[str] = []
    jobs: dict[str, FakeJobState] = {}
    runtime_specs: dict[str, dict[str, Any]] = {}

    async def _ensure_provider_ready_for_job_create() -> None:
        provider_ready_calls.append("ready")

    async def _persist_snapshot(job_id: str, force: bool) -> None:
        persist_calls.append((job_id, force))

    def _schedule_extraction_job_task(**kwargs) -> bool:
        schedule_calls.append(dict(kwargs))
        return True

    job_runtime = _build_job_runtime(
        jobs=jobs,
        runtime_specs=runtime_specs,
        cleanup_jobs_locked=lambda: cleanup_calls.append("cleanup"),
        persist_snapshot=_persist_snapshot,
        schedule_extraction_job_task=_schedule_extraction_job_task,
    )
    runtime = _build_runtime(
        extraction_job_runtime=job_runtime,
        ensure_provider_ready_for_job_create=_ensure_provider_ready_for_job_create,
    )

    async def _scenario() -> dict[str, Any]:
        return await runtime.create_job(
            request=SimpleNamespace(headers={}),
            files=[FakeUpload("demo.pdf", b"%PDF-1.4", "application/pdf")],
            schema_form='{"fields":["amount"]}',
            tenant_id="tenant-a",
        )

    payload = asyncio.run(_scenario())

    job_id = payload["job_id"]
    assert payload["status"] == "queued"
    assert job_id in jobs
    assert provider_ready_calls == ["ready"]
    assert cleanup_calls == ["cleanup"]
    assert persist_calls == [(job_id, True)]
    assert schedule_calls and schedule_calls[0]["job_id"] == job_id
    assert schedule_calls[0]["tenant_id"] == "tenant-a"
    assert runtime_specs[job_id]["max_retries"] == 3
    assert runtime_specs[job_id]["loaded_files"][0]["file_name"] == "demo.pdf"


def test_extraction_request_runtime_extract_batch_wraps_errors_and_syncs(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_BATCH_CONCURRENCY", "2")

    provider_ready_calls: list[str] = []
    sync_calls: list[dict[str, Any]] = []

    async def _process_single_doc_bytes(**kwargs):
        if kwargs["file_name"] == "bad.pdf":
            raise RuntimeError("boom")
        return FakeDocument(
            file_name=kwargs["file_name"],
            file_hash=f"hash-{kwargs['file_name']}",
            track="VisualTrack",
            cached=False,
            result={"ok": True},
            errors=[],
            diagnostics={},
        )

    async def _ensure_provider_ready_for_job_create() -> None:
        provider_ready_calls.append("ready")

    async def _enqueue_document_sync_for_seed(**kwargs) -> bool:
        sync_calls.append(dict(kwargs))
        return True

    runtime = _build_runtime(
        process_single_doc_bytes=_process_single_doc_bytes,
        ensure_provider_ready_for_job_create=_ensure_provider_ready_for_job_create,
        module4_sync_callback_bundle=FakeModule4SyncCallbackBundle(
            enqueue_for_seed=_enqueue_document_sync_for_seed
        ),
    )

    async def _scenario():
        return await runtime.extract_batch(
            request=SimpleNamespace(headers={}),
            files=[
                FakeUpload("ok.pdf", b"%PDF-ok", "application/pdf"),
                FakeUpload("bad.pdf", b"%PDF-bad", "application/pdf"),
            ],
            schema_form='{"fields":["amount"]}',
            tenant_id="tenant-a",
        )

    payload = asyncio.run(_scenario())

    assert provider_ready_calls == ["ready"]
    assert len(payload.documents) == 2
    assert payload.documents[0].file_name == "ok.pdf"
    assert payload.documents[1].file_name == "bad.pdf"
    assert payload.documents[1].errors == ["boom"]
    assert sync_calls and sync_calls[0]["tenant_id"] == "tenant-a"
    assert sync_calls[0]["mode"] == "default"
    assert len(sync_calls[0]["documents"]) == 2


def test_extraction_request_runtime_get_job_status_restores_snapshot() -> None:
    restore_calls: list[str] = []
    restored_job = FakeJobState(
        job_id="extract_job_restored",
        status="completed",
        created_at=1.0,
        updated_at=2.0,
        total_files=1,
        completed_files=1,
        failed_files=0,
        current_file_index=1,
        current_file_name="demo.pdf",
        current_stage="completed",
        files=[],
        documents=[],
        errors=[],
    )

    async def _restore_job_from_snapshot(job_id: str):
        restore_calls.append(job_id)
        return restored_job

    job_runtime = _build_job_runtime(restore_job_from_snapshot=_restore_job_from_snapshot)
    runtime = _build_runtime(extraction_job_runtime=job_runtime)

    async def _scenario() -> dict[str, Any]:
        return await runtime.get_job_status("extract_job_restored", include_documents=True)

    payload = asyncio.run(_scenario())

    assert restore_calls == ["extract_job_restored"]
    assert payload == {
        "job_id": "extract_job_restored",
        "status": "completed",
        "include_documents": True,
    }
