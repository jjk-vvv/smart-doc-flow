from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.modules.module2.composition.http_runtime_bundle import build_module2_http_runtime_bundle


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

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "track": self.track,
            "cached": self.cached,
            "result": self.result,
            "errors": list(self.errors),
            "diagnostics": dict(self.diagnostics),
        }


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


class _FakeOfficePreviewRuntime:
    def __init__(self) -> None:
        self.ensure_calls: list[dict[str, Any]] = []

    async def ensure_job_started(self, *, file_name: str, file_bytes: bytes, file_hash: str) -> Any:
        self.ensure_calls.append(
            {
                "file_name": file_name,
                "file_bytes": file_bytes,
                "file_hash": file_hash,
            }
        )
        return SimpleNamespace(job_id=f"preview-{file_hash[:8]}")

    def serialize_job(self, job: Any) -> dict[str, Any]:
        return {"job_id": job.job_id}

    async def get_status_payload(self, job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "status": "completed"}


class _FakeModule4SyncCallbackBundle:
    def __init__(self) -> None:
        self.seed_calls: list[dict[str, Any]] = []

    async def enqueue_document_sync_for_seed(self, **kwargs) -> bool:
        self.seed_calls.append(dict(kwargs))
        return False


def test_http_runtime_bundle_builds_shared_extraction_chain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_MAX_RETRIES", "2")

    workflow_calls: list[dict[str, Any]] = []
    provider_calls: list[str] = []
    office_preview_runtime = _FakeOfficePreviewRuntime()
    module4_sync_callback_bundle = _FakeModule4SyncCallbackBundle()

    async def _process_single_doc_bytes(**kwargs):
        workflow_calls.append(dict(kwargs))
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
        provider_calls.append("ready")

    async def _triage(file_name: str, file_bytes: bytes, schema_digest: str):
        return SimpleNamespace(
            cached_payload=None,
            file_name=file_name,
            file_bytes_len=len(file_bytes),
            schema_digest=schema_digest,
        )

    bundle = build_module2_http_runtime_bundle(
        module2_root=tmp_path,
        artifact_root_factory=lambda: tmp_path / "artifacts",
        resolve_module2_path=lambda raw, default: Path(raw).resolve() if raw else default.resolve(),
        extraction_job_state_root_factory=lambda: tmp_path / "job-state",
        safe_artifact_path=lambda path_fragment: tmp_path / path_fragment,
        process_single_doc_bytes=_process_single_doc_bytes,
        parse_schema_form_json=lambda raw_schema: {"raw": raw_schema},
        write_artifact_bytes=lambda **kwargs: (
            f"preview/uploaded/{kwargs['file_name']}",
            f"/extract/artifact/preview/uploaded/{kwargs['file_name']}",
        ),
        schema_hash=lambda schema: f"schema:{sorted(schema.keys())}",
        build_stream_router=lambda: SimpleNamespace(triage=_triage),
        ensure_provider_ready_for_job_create=_ensure_provider_ready_for_job_create,
        module4_tenant=lambda request, explicit="": explicit or "tenant-default",
        job_state_factory=FakeJobState,
        job_file_state_factory=FakeFileState,
        document_validate=lambda item: item,
        extraction_result_factory=lambda payload: payload,
        document_response_factory=FakeDocument,
        batch_response_factory=lambda documents: SimpleNamespace(documents=documents),
        module4_sync_callback_bundle=module4_sync_callback_bundle,
        office_preview_runtime=office_preview_runtime,
        is_word_file=lambda file_name: file_name.lower().endswith((".doc", ".docx")),
        office_convert_enabled=lambda: True,
        summarize_document_payload=lambda payload: f"summary:{payload.file_name}",
        build_document_trace_hits=lambda **kwargs: [],
        filter_trace_hits=lambda hits, **kwargs: hits,
        summarize_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        trace_locate_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        bounded_env_int=lambda name, default, **kwargs: default,
        logger=logging.getLogger("test-http-runtime-bundle"),
    )

    async def _scenario() -> tuple[dict[str, Any], dict[str, Any]]:
        job_payload = await bundle.extraction_request_runtime.create_job(
            request=SimpleNamespace(headers={}),
            files=[FakeUpload("demo.pdf", b"%PDF-1.4", "application/pdf")],
            schema_form='{"fields":["amount"]}',
            tenant_id="tenant-a",
        )
        job_id = str(job_payload["job_id"])
        await bundle.extraction_job_tasks[job_id]
        preview_payload = await bundle.office_preview_request_runtime.start(
            FakeUpload("demo.docx", b"docx-bytes")
        )
        return job_payload, preview_payload

    job_payload, preview_payload = asyncio.run(_scenario())

    job_id = str(job_payload["job_id"])
    job_state = bundle.extraction_jobs[job_id]
    assert provider_calls == ["ready"]
    assert workflow_calls and workflow_calls[0]["file_name"] == "demo.pdf"
    assert workflow_calls[0]["schema"] == {"raw": '{"fields":["amount"]}'}
    assert job_state.status == "completed"
    assert job_state.completed_files == 1
    assert bundle.extraction_jobs is bundle.extraction_job_runtime.jobs
    assert bundle.extraction_lock is bundle.extraction_job_runtime.lock
    assert bundle.extraction_job_runtime_specs is bundle.extraction_job_runtime.runtime_specs
    assert bundle.extraction_job_tasks is bundle.extraction_job_runtime.tasks
    assert bundle.extraction_job_persist_markers is bundle.extraction_job_runtime.persist_markers
    assert bundle.extraction_request_runtime._extraction_job_runtime is bundle.extraction_job_runtime
    assert bundle.extraction_request_runtime._module4_sync_callback_bundle is module4_sync_callback_bundle
    assert callable(bundle.extraction_request_runtime._document_validate)
    assert bundle.extraction_job_executor._extraction_job_runtime is bundle.extraction_job_runtime
    assert bundle.extraction_job_executor._module4_sync_callback_bundle is module4_sync_callback_bundle
    assert preview_payload["job_id"].startswith("preview-")
    assert office_preview_runtime.ensure_calls[0]["file_name"] == "demo.docx"
