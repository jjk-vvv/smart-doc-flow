from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

import app.composition.application as module4_main  # noqa: E402
from app.schemas import IngestRequest  # noqa: E402


def _request() -> Request:
    return Request({"type": "http", "headers": []})


class FakeDocumentStorage:
    def __init__(self) -> None:
        self.graph_file_rows: list[dict] = []
        self.graph_versions: list[dict] = []

    async def list_rules(self, enabled_only: bool = False) -> list[dict]:
        return []

    async def upsert_graph_file(self, **kwargs):
        row = {"graph_file_id": f"graph-file-{len(self.graph_file_rows) + 1}", **kwargs}
        self.graph_file_rows.append(row)
        return row

    async def add_graph_version(self, **kwargs):
        row = {"graph_version_id": f"graph-version-{len(self.graph_versions) + 1}", **kwargs}
        self.graph_versions.append(row)
        return row


class FakeSubmitStorage:
    def __init__(self) -> None:
        self.created_job: dict | None = None
        self.created_batch: dict | None = None
        self.existing_batch: dict | None = None
        self.existing_job: dict | None = None

    async def get_ingest_batch(self, **kwargs):
        return self.existing_batch

    async def get_job(self, job_id: str, tenant_id: str | None = None):
        if self.existing_job and self.existing_job.get("job_id") == job_id:
            return self.existing_job
        if self.created_job and self.created_job.get("job_id") == job_id:
            return self.created_job
        return None

    async def create_job(self, **kwargs):
        self.created_job = {
            "job_id": "job-1",
            "tenant_id": kwargs["tenant_id"],
            "job_type": kwargs["job_type"],
            "status": kwargs["status"],
            "payload": kwargs["payload"],
        }
        return self.created_job

    async def create_ingest_batch(self, **kwargs):
        self.created_batch = {
            "batch_id": "batch-1",
            "tenant_id": kwargs["tenant_id"],
            "source": kwargs["source"],
            "source_batch_key": kwargs["source_batch_key"],
            "job_id": kwargs["job_id"],
            "raw_payload": kwargs["raw_payload"],
        }
        return self.created_batch


def test_run_document_ingest_job_marks_processing_then_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_storage = FakeDocumentStorage()
    recorded_stages: list[dict] = []

    async def fake_update_job_stage(job_id: str, **kwargs):
        recorded_stages.append({"job_id": job_id, **kwargs})

    async def fake_process_document(**kwargs):
        assert kwargs["tenant_id"] == "tenant-a"
        assert kwargs["batch_id"] == "batch-a"
        assert kwargs["doc"]["file_name"] == "report.pdf"
        return {"nodes": 5, "edges": 4, "alerts": 2, "evidence": 3}

    module4_main._set_runtime_ref("storage", fake_storage)
    monkeypatch.setattr(module4_main, "_update_job_stage", fake_update_job_stage)
    monkeypatch.setattr(module4_main.module4_app_runtime, "_process_document_fn", fake_process_document)

    payload = IngestRequest(
        tenant_id="tenant-a",
        source="module2",
        documents=[{"file_name": "report.pdf", "file_hash": "hash-report", "track": "alpha"}],
    )

    result = asyncio.run(module4_main._run_document_ingest_job("job-a", "batch-a", payload))

    assert result == {
        "stage": "processing_documents",
        "nodes": 5,
        "edges": 4,
        "alerts": 2,
        "evidence": 3,
        "documents": 1,
        "skipped_documents": 0,
        "uploads": 0,
    }
    assert [row["status"] for row in fake_storage.graph_file_rows] == ["processing_documents", "ready"]
    assert fake_storage.graph_file_rows[0]["metadata"]["stage"] == "processing_documents"
    assert fake_storage.graph_file_rows[1]["metadata"]["stage"] == "ready"
    assert fake_storage.graph_versions[0]["status"] == "ready"
    assert recorded_stages[0]["stage"] == "processing_documents"
    assert recorded_stages[-1]["progress"] == 100.0


def test_run_document_ingest_job_marks_failed_graph_file_on_document_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = FakeDocumentStorage()
    recorded_stages: list[dict] = []

    async def fake_update_job_stage(job_id: str, **kwargs):
        recorded_stages.append({"job_id": job_id, **kwargs})

    async def fake_process_document(**kwargs):
        raise ValueError("document exploded")

    module4_main._set_runtime_ref("storage", fake_storage)
    monkeypatch.setattr(module4_main, "_update_job_stage", fake_update_job_stage)
    monkeypatch.setattr(module4_main.module4_app_runtime, "_process_document_fn", fake_process_document)

    payload = IngestRequest(
        tenant_id="tenant-b",
        source="module2",
        documents=[{"file_name": "broken.pdf", "file_hash": "hash-broken"}],
    )

    with pytest.raises(ValueError, match="document exploded"):
        asyncio.run(module4_main._run_document_ingest_job("job-b", "batch-b", payload))

    assert [row["status"] for row in fake_storage.graph_file_rows] == ["processing_documents", "failed"]
    failed_row = fake_storage.graph_file_rows[-1]
    assert failed_row["metadata"]["stage"] == "failed"
    assert failed_row["metadata"]["failure_stage"] == "processing_documents"
    assert failed_row["metadata"]["failure_category"] == "document_ingest_failed"
    assert "document exploded" in failed_row["metadata"]["failure_message"]
    assert fake_storage.graph_versions == []
    assert recorded_stages[0]["stage"] == "processing_documents"


def test_submit_ingest_job_rejects_non_module2_source() -> None:
    payload = IngestRequest.model_construct(
        tenant_id="tenant-c",
        source="legacy-upload",
        source_batch_key=None,
        graph_mode="hybrid",
        documents=[{"file_name": "a.pdf", "file_hash": "hash-a"}],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(module4_main._submit_ingest_job(payload, _request()))

    assert exc_info.value.status_code == 400
    assert "only accepts document sync from module2" in str(exc_info.value.detail)


def test_submit_ingest_job_rejects_empty_documents() -> None:
    payload = IngestRequest.model_construct(
        tenant_id="tenant-d",
        source="module2",
        source_batch_key=None,
        graph_mode="hybrid",
        documents=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(module4_main._submit_ingest_job(payload, _request()))

    assert exc_info.value.status_code == 400
    assert "graph-eligible documents found" in str(exc_info.value.detail)


def test_submit_ingest_job_creates_documents_only_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_storage = FakeSubmitStorage()
    scheduled: list[tuple[str, str, str]] = []

    def fake_schedule_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
        scheduled.append((job_id, batch_id, payload.tenant_id))

    module4_main._set_runtime_ref("storage", fake_storage)
    monkeypatch.setattr(module4_main, "_schedule_ingest_job", fake_schedule_ingest_job)

    payload = IngestRequest(
        tenant_id="tenant-e",
        source="module2",
        documents=[
            {"file_name": "a.pdf", "file_hash": "hash-a"},
            {"file_name": "b.pdf", "file_hash": "hash-b"},
        ],
    )

    response = asyncio.run(module4_main._submit_ingest_job(payload, _request()))

    assert response.job_id == "job-1"
    assert response.batch_id == "batch-1"
    assert response.status == "queued"
    assert fake_storage.created_job is not None
    assert fake_storage.created_job["payload"]["documents"] == 2
    assert fake_storage.created_job["payload"]["inputs"] == 2
    assert "uploads" not in fake_storage.created_job["payload"]
    assert fake_storage.created_batch is not None
    assert fake_storage.created_batch["raw_payload"]["documents"][0]["file_name"] == "a.pdf"
    assert scheduled == [("job-1", "batch-1", "tenant-e")]


def test_submit_ingest_job_accepts_text_corpus_and_synthesizes_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = FakeSubmitStorage()
    scheduled: list[tuple[str, str, str]] = []

    def fake_schedule_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
        scheduled.append((job_id, batch_id, payload.tenant_id))

    module4_main._set_runtime_ref("storage", fake_storage)
    monkeypatch.setattr(module4_main, "_schedule_ingest_job", fake_schedule_ingest_job)

    payload = IngestRequest(
        tenant_id="tenant-f",
        source="module2",
        text_corpus="这是来自文本语料的直接输入。",
        settings_overrides={"chunk_size": 900, "chunk_overlap": 80},
        metadata={"file_name": "direct-text.md", "track": "direct-ingest"},
    )

    response = asyncio.run(module4_main._submit_ingest_job(payload, _request()))

    assert response.job_id == "job-1"
    assert response.batch_id == "batch-1"
    assert response.status == "queued"
    assert fake_storage.created_job is not None
    assert fake_storage.created_job["payload"]["documents"] == 1
    assert fake_storage.created_batch is not None
    created_doc = fake_storage.created_batch["raw_payload"]["documents"][0]
    assert created_doc["file_name"] == "direct-text.md"
    assert created_doc["track"] == "direct-ingest"
    assert created_doc["text_corpus"] == "这是来自文本语料的直接输入。"
    assert created_doc["settings_overrides"]["chunk_size"] == 900
    assert scheduled == [("job-1", "batch-1", "tenant-f")]
