from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path


extraction_job_module = import_module("app.modules.module2.services.extraction.job")
ExtractionJobRuntime = extraction_job_module.ExtractionJobRuntime


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
    payload: dict

    def model_dump(self, mode: str = "json") -> dict:
        return dict(self.payload)


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


def _safe_artifact_path_factory(root: Path):
    def _safe_artifact_path(path_fragment: str) -> Path:
        target = (root / str(path_fragment or "").strip().strip("/")).resolve()
        target.relative_to(root.resolve())
        return target

    return _safe_artifact_path


def _build_runtime(tmp_path: Path, run_extraction_job):
    state_root = tmp_path / "state"
    artifact_root = tmp_path / "artifacts"
    state_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    return ExtractionJobRuntime(
        state_root_factory=lambda: state_root,
        safe_artifact_path=_safe_artifact_path_factory(artifact_root),
        job_state_factory=FakeJobState,
        job_file_state_factory=FakeFileState,
        document_validate=lambda item: FakeDocument(
            file_name=str(item.get("file_name") or ""),
            file_hash=str(item.get("file_hash") or ""),
            payload=dict(item),
        ),
        run_extraction_job=run_extraction_job,
        logger=logging.getLogger("test-extraction-job-runtime"),
    )


def test_extraction_job_runtime_persists_and_restores_terminal_job(tmp_path: Path) -> None:
    async def _run_job(**kwargs) -> None:
        return None

    runtime = _build_runtime(tmp_path, _run_job)
    job_id = "extract_job_terminal"
    artifact_path = "uploaded/demo.txt"
    artifact_file = runtime._safe_artifact_path(artifact_path)
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text("hello", encoding="utf-8")

    job = FakeJobState(
        job_id=job_id,
        status="completed",
        created_at=1.0,
        updated_at=2.0,
        total_files=1,
        completed_files=1,
        failed_files=0,
        current_file_index=1,
        current_file_name="demo.txt",
        current_stage="completed",
        files=[
            FakeFileState(
                file_name="demo.txt",
                file_hash="hash-1",
                status="completed",
                stage="completed",
                progress_ratio=1.0,
                message="done",
                artifact_path=artifact_path,
                artifact_url="/extract/artifact/uploaded/demo.txt",
            )
        ],
        documents=[
            FakeDocument(
                file_name="demo.txt",
                file_hash="hash-1",
                payload={"file_name": "demo.txt", "file_hash": "hash-1", "result": {"a": 1}},
            )
        ],
        errors=[],
    )
    runtime.jobs[job_id] = job
    runtime.runtime_specs[job_id] = {
        "schema": {"fields": ["a"]},
        "schema_digest": "schema-1",
        "max_retries": 2,
        "tenant_id": "tenant-a",
        "loaded_files": [
            {
                "file_name": "demo.txt",
                "file_hash": "hash-1",
                "artifact_path": artifact_path,
                "artifact_url": "/extract/artifact/uploaded/demo.txt",
                "mime_type": "text/plain",
            }
        ],
    }

    async def _scenario() -> None:
        await runtime.persist_snapshot(job_id, force=True)
        runtime.jobs.clear()
        runtime.runtime_specs.clear()
        runtime.tasks.clear()
        runtime.persist_markers.clear()
        restored = await runtime.restore_from_snapshot(job_id)

        assert restored is not None
        assert restored.job_id == job_id
        assert restored.terminal() is True
        payload = runtime.serialize_job(restored, include_documents=True)
        assert payload["documents"][0]["file_name"] == "demo.txt"
        assert payload["files"][0]["artifact_path"] == artifact_path
        assert runtime.tasks == {}

    asyncio.run(_scenario())


def test_extraction_job_runtime_restores_pending_job_and_schedules_task(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[dict] = []

    async def _run_job(**kwargs) -> None:
        calls.append(dict(kwargs))
        started.set()
        await release.wait()

    runtime = _build_runtime(tmp_path, _run_job)
    job_id = "extract_job_pending"
    artifact_path = "uploaded/demo.pdf"
    artifact_file = runtime._safe_artifact_path(artifact_path)
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_bytes(b"%PDF-1.4")
    snapshot_job = FakeJobState(
        job_id=job_id,
        status="running",
        created_at=1.0,
        updated_at=2.0,
        total_files=1,
        completed_files=0,
        failed_files=0,
        current_file_index=1,
        current_file_name="demo.pdf",
        current_stage="parsing",
        files=[
            FakeFileState(
                file_name="demo.pdf",
                file_hash="hash-2",
                status="running",
                stage="parsing",
                progress_ratio=0.5,
                message="working",
                artifact_path=artifact_path,
                artifact_url="/extract/artifact/uploaded/demo.pdf",
            )
        ],
        documents=[],
        errors=[],
    )
    snapshot_payload = {
        "version": 1,
        "saved_at": 2.0,
        "job": runtime.serialize_job(snapshot_job, include_documents=True),
        "runtime": {
            "schema": {"fields": ["b"]},
            "schema_digest": "schema-2",
            "max_retries": 1,
            "tenant_id": "tenant-b",
            "loaded_files": [
                {
                    "file_name": "demo.pdf",
                    "file_hash": "hash-2",
                    "artifact_path": artifact_path,
                    "artifact_url": "/extract/artifact/uploaded/demo.pdf",
                    "mime_type": "application/pdf",
                }
            ],
        },
    }
    runtime.state_path(job_id).write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _scenario() -> None:
        restored = await runtime.restore_from_snapshot(job_id)
        assert restored is not None
        await asyncio.wait_for(started.wait(), timeout=2.0)
        assert job_id in runtime.tasks
        assert calls and calls[0]["job_id"] == job_id
        release.set()
        await asyncio.gather(*list(runtime.tasks.values()), return_exceptions=True)

    asyncio.run(_scenario())


def test_extraction_job_runtime_register_job_builds_state_and_schedules_task(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[dict] = []

    async def _run_job(**kwargs) -> None:
        calls.append(dict(kwargs))
        started.set()
        await release.wait()

    runtime = _build_runtime(tmp_path, _run_job)
    artifact_path = "uploaded/demo.pdf"
    artifact_file = runtime._safe_artifact_path(artifact_path)
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_bytes(b"%PDF-1.4")
    loaded_files = [
        (
            "demo.pdf",
            b"%PDF-1.4",
            "hash-3",
            artifact_path,
            "/extract/artifact/uploaded/demo.pdf",
            "application/pdf",
        )
    ]

    async def _scenario() -> None:
        job = await runtime.register_job(
            loaded_files=loaded_files,
            schema_obj={"fields": ["amount"]},
            schema_digest="schema-3",
            max_retries=2,
            tenant_id="tenant-c",
        )
        job_id = job.job_id

        assert job_id in runtime.jobs
        assert runtime.runtime_specs[job_id]["tenant_id"] == "tenant-c"
        assert runtime.runtime_specs[job_id]["loaded_files"][0]["file_name"] == "demo.pdf"

        snapshot_payload = json.loads(runtime.state_path(job_id).read_text(encoding="utf-8"))
        assert snapshot_payload["job"]["status"] == "queued"
        assert snapshot_payload["runtime"]["schema_digest"] == "schema-3"
        assert snapshot_payload["runtime"]["loaded_files"][0]["artifact_path"] == artifact_path

        await asyncio.wait_for(started.wait(), timeout=2.0)
        assert calls and calls[0]["job_id"] == job_id
        assert calls[0]["loaded_files"][0][0] == "demo.pdf"

        release.set()
        await asyncio.gather(*list(runtime.tasks.values()), return_exceptions=True)

    asyncio.run(_scenario())
