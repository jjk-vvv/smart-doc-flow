from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


module4_sync_outbox_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "module4_sync_outbox_runtime.py"],
    "_smart_doc_flow_module2_module4_sync_outbox_runtime",
)

Module4SyncOutboxRuntime = module4_sync_outbox_runtime_module.Module4SyncOutboxRuntime


class _DumpableDocument:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = dict(payload)

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        assert mode == "json"
        return dict(self._payload)


class _FakeLogger:
    def __init__(self) -> None:
        self.infos: list[tuple[object, ...]] = []
        self.warnings: list[tuple[object, ...]] = []

    def info(self, *args) -> None:
        self.infos.append(args)

    def warning(self, *args) -> None:
        self.warnings.append(args)


class _FakeMetricsRuntime:
    def __init__(self) -> None:
        self.attempts = 0
        self.successes: list[dict[str, object]] = []
        self.failures: list[dict[str, object]] = []

    def mark_attempt(self) -> None:
        self.attempts += 1

    def mark_success(self, *, response_payload, endpoint: str, source_batch_key: str) -> None:
        self.successes.append(
            {
                "response_payload": dict(response_payload),
                "endpoint": endpoint,
                "source_batch_key": source_batch_key,
            }
        )

    def mark_failure(self, *, message: str, endpoint: str, source_batch_key: str) -> None:
        self.failures.append(
            {
                "message": message,
                "endpoint": endpoint,
                "source_batch_key": source_batch_key,
            }
        )


class _SuccessStorage:
    def __init__(self) -> None:
        self.delivered: list[tuple[str, dict[str, object]]] = []
        self.claimed = 0

    async def get_graph_sync_outbox(self, outbox_id: str):
        return {
            "outbox_id": outbox_id,
            "status": "pending",
        }

    async def claim_graph_sync_outbox(self, outbox_id: str):
        self.claimed += 1
        return {
            "outbox_id": outbox_id,
            "endpoint": "/module4/ingest",
            "tenant_id": "tenant-a",
            "source": "module2",
            "source_batch_key": "batch-a",
            "file_hash": "file-a",
            "payload_json": {"hello": "world"},
            "attempt_count": 1,
            "max_attempts": 2,
        }

    async def mark_graph_sync_outbox_delivered(self, *, outbox_id: str, response_payload):
        self.delivered.append((outbox_id, dict(response_payload)))

    async def requeue_graph_sync_outbox(self, **kwargs):
        raise AssertionError("should not requeue success path")

    async def mark_graph_sync_outbox_failed(self, **kwargs):
        raise AssertionError("should not fail success path")


class _FailureStorage:
    def __init__(self) -> None:
        self.failed: list[tuple[str, str]] = []
        self.requeued = 0

    async def get_graph_sync_outbox(self, outbox_id: str):
        return {
            "outbox_id": outbox_id,
            "status": "pending",
        }

    async def claim_graph_sync_outbox(self, outbox_id: str):
        return {
            "outbox_id": outbox_id,
            "endpoint": "/module4/ingest",
            "tenant_id": "tenant-b",
            "source": "module2",
            "source_batch_key": "batch-b",
            "file_hash": "file-b",
            "payload_json": {"bad": True},
            "attempt_count": 2,
            "max_attempts": 2,
        }

    async def mark_graph_sync_outbox_delivered(self, **kwargs):
        raise AssertionError("should not deliver failed path")

    async def requeue_graph_sync_outbox(self, **kwargs):
        self.requeued += 1

    async def mark_graph_sync_outbox_failed(self, *, outbox_id: str, error_message: str):
        self.failed.append((outbox_id, error_message))


class _EnqueueStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def upsert_graph_sync_outbox(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"outbox_id": "outbox-enqueue-1"}


class _RecoverStorage:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def recover_pending_graph_sync_outbox(self, *, limit: int = 200):
        self.limits.append(limit)
        return [
            {"outbox_id": "outbox-r1"},
            {"outbox_id": ""},
            {"outbox_id": "outbox-r2"},
        ]


def _build_runtime(*, outbox_repository, metrics_runtime, logger, transport):
    return Module4SyncOutboxRuntime(
        logger=logger,
        outbox_repository=outbox_repository,
        metrics_runtime=metrics_runtime,
        base_url_factory=lambda: "https://module4.example",
        headers_factory=lambda tenant_id: {"X-Tenant-Id": tenant_id},
        timeout_factory=lambda: 12.0,
        retries_factory=lambda: 1,
        retryable_status=lambda status_code: status_code in {408, 429, 500, 502, 503, 504},
        delay_factory=lambda attempt_index: 0.0,
        utcnow_factory=lambda: datetime.now(timezone.utc),
        default_tenant_factory=lambda: "default",
        transport=transport,
        sleep_fn=lambda seconds: asyncio.sleep(0),
    )


def test_module4_sync_outbox_runtime_delivers_successfully() -> None:
    logger = _FakeLogger()
    metrics = _FakeMetricsRuntime()
    storage = _SuccessStorage()
    runtime = _build_runtime(
        outbox_repository=storage,
        metrics_runtime=metrics,
        logger=logger,
        transport=lambda url, headers, data, timeout_sec: asyncio.sleep(0, result=(200, '{"job_id":"job-1","batch_id":"batch-1"}')),
    )

    async def _run() -> None:
        await runtime.deliver_outbox("outbox-1")

    asyncio.run(_run())

    assert metrics.attempts == 1
    assert metrics.successes == [
        {
            "response_payload": {"job_id": "job-1", "batch_id": "batch-1"},
            "endpoint": "/module4/ingest",
            "source_batch_key": "batch-a",
        }
    ]
    assert metrics.failures == []
    assert storage.delivered == [("outbox-1", {"job_id": "job-1", "batch_id": "batch-1"})]
    assert logger.infos[-1][0] == "module2 delivered module4 sync outbox=%s source=%s file=%s batch=%s attempt=%s/%s endpoint=%s"


def test_module4_sync_outbox_runtime_marks_permanent_failure() -> None:
    logger = _FakeLogger()
    metrics = _FakeMetricsRuntime()
    storage = _FailureStorage()
    runtime = _build_runtime(
        outbox_repository=storage,
        metrics_runtime=metrics,
        logger=logger,
        transport=lambda url, headers, data, timeout_sec: asyncio.sleep(0, result=(500, "server down")),
    )

    async def _run() -> None:
        await runtime.deliver_outbox("outbox-2")

    asyncio.run(_run())

    assert metrics.attempts == 1
    assert metrics.successes == []
    assert metrics.failures == [
        {
            "message": "HTTPError 500: server down",
            "endpoint": "/module4/ingest",
            "source_batch_key": "batch-b",
        }
    ]
    assert storage.requeued == 0
    assert storage.failed == [("outbox-2", "HTTPError 500: server down")]
    assert logger.warnings[-1][0] == "module2 -> module4 outbox permanently failed outbox=%s file=%s batch=%s attempt=%s/%s: %s"


def test_module4_sync_outbox_runtime_serializes_row_and_payload_summary() -> None:
    row = {
        "outbox_id": "outbox-3",
        "tenant_id": "tenant-c",
        "source": "module2",
        "source_batch_key": "batch-c",
        "endpoint": "/module4/ingest",
        "sync_kind": "document_batch",
        "file_hash": "file-c",
        "status": "pending",
        "attempt_count": 1,
        "max_attempts": 3,
        "last_error": "",
        "next_attempt_at": None,
        "last_attempt_at": None,
        "delivered_at": None,
        "created_at": None,
        "updated_at": None,
        "payload_json": {
            "tenant_id": "tenant-c",
            "source": "module2",
            "source_batch_key": "batch-c",
            "documents": [
                {
                    "file_name": "a.pdf",
                    "file_hash": "hash-a",
                    "track": "VisualTrack",
                    "result": {"field": {"value": "x"}},
                    "trace_hits": [{"id": 1}],
                    "errors": [],
                    "soft_warnings": ["warn-1"],
                    "diagnostics": {"quality_status": "ok"},
                    "cached": True,
                }
            ],
        },
        "last_response_json": {"job_id": "job-c", "batch_id": "batch-c", "status": "queued"},
    }

    view = Module4SyncOutboxRuntime.serialize_outbox_row(row, include_payload=True)

    assert view["payload_summary"]["document_count"] == 1
    assert view["payload_summary"]["documents"][0]["file_name"] == "a.pdf"
    assert view["response_summary"] == {"job_id": "job-c", "batch_id": "batch-c", "status": "queued"}
    assert view["payload_json"]["tenant_id"] == "tenant-c"


def test_module4_sync_outbox_runtime_parses_string_payload() -> None:
    payload = Module4SyncOutboxRuntime.outbox_payload(
        {"payload_json": '{"tenant_id":"tenant-d","source":"module2"}'}
    )
    assert payload == {"tenant_id": "tenant-d", "source": "module2"}


def test_module4_sync_outbox_runtime_normalizes_documents_and_builds_stable_batch_key() -> None:
    documents = [
        {"file_name": "a.pdf", "file_hash": "hash-a"},
        _DumpableDocument({"file_name": "b.pdf", "file_hash": "hash-b", "result": {"title": "B"}}),
        "skip-me",
    ]

    normalized = Module4SyncOutboxRuntime.normalize_documents(documents)
    key_a = Module4SyncOutboxRuntime.source_batch_key(
        source="module2",
        tenant_id="tenant-e",
        documents=documents,
        seed="seed-1",
    )
    key_b = Module4SyncOutboxRuntime.source_batch_key(
        source="module2",
        tenant_id="tenant-e",
        documents=normalized,
        seed="seed-1",
    )
    key_c = Module4SyncOutboxRuntime.source_batch_key(
        source="module2",
        tenant_id="tenant-e",
        documents=normalized,
        seed="seed-2",
    )

    assert normalized == [
        {
            "file_name": "a.pdf",
            "file_hash": "hash-a",
            "text_corpus": "Document a.pdf",
            "source_texts": [{"kind": "text_corpus", "text": "Document a.pdf", "quality_weight": 0.95}],
            "settings_overrides": {},
        },
        {
            "file_name": "b.pdf",
            "file_hash": "hash-b",
            "result": {"title": "B"},
            "text_corpus": "Document b.pdf",
            "source_texts": [{"kind": "text_corpus", "text": "Document b.pdf", "quality_weight": 0.95}],
            "settings_overrides": {},
        },
    ]
    assert key_a == key_b
    assert len(key_a) == 32
    assert key_c != key_a


def test_module4_sync_outbox_runtime_enqueue_document_sync_upserts_and_schedules() -> None:
    logger = _FakeLogger()
    metrics = _FakeMetricsRuntime()
    storage = _EnqueueStorage()
    runtime = _build_runtime(
        outbox_repository=storage,
        metrics_runtime=metrics,
        logger=logger,
        transport=lambda url, headers, data, timeout_sec: asyncio.sleep(0, result=(200, "{}")),
    )
    scheduled: list[str] = []

    async def _run() -> None:
        await runtime.enqueue_document_sync(
            source="module2",
            tenant_id="tenant-f",
            documents=[_DumpableDocument({"file_name": "c.pdf", "file_hash": "hash-c", "track": "VisualTrack"})],
            source_batch_key="batch-f",
            schedule_outbox=scheduled.append,
        )

    asyncio.run(_run())

    assert scheduled == ["outbox-enqueue-1"]
    assert storage.calls == [
        {
            "tenant_id": "tenant-f",
            "source": "module2",
            "source_batch_key": "batch-f",
            "endpoint": "/module4/ingest",
            "payload": {
                "tenant_id": "tenant-f",
                "source": "module2",
                "source_batch_key": "batch-f",
                "documents": [
                    {
                            "file_name": "c.pdf",
                            "file_hash": "hash-c",
                            "track": "VisualTrack",
                            "text_corpus": "Document c.pdf",
                            "source_texts": [
                                {"kind": "text_corpus", "text": "Document c.pdf", "quality_weight": 0.95}
                            ],
                            "settings_overrides": {},
                        }
                    ],
                },
            "sync_kind": "document_batch",
            "file_hash": "hash-c",
            "max_attempts": 2,
        }
    ]


def test_module4_sync_outbox_runtime_builds_text_corpus_and_source_texts_from_diagnostics() -> None:
    documents = [
        {
            "file_name": "doc.md",
            "file_hash": "hash-z",
            "result": {"主题": {"value": "浙江省生态环境质量"}},
            "trace_hits": [{"snippet": "图表显示空气质量持续改善"}],
            "diagnostics": {
                "assistant1_source_markdown_artifact_path": "assistant_1_source/abc/doc.md",
                "assistant_payload_artifact_path": "assistant_payload/abc/doc.json",
            },
            "markdown": "正文段落一\n正文段落二",
        }
    ]

    normalized = Module4SyncOutboxRuntime.normalize_documents(documents)

    assert len(normalized) == 1
    doc = normalized[0]
    assert "主题: 浙江省生态环境质量" in doc["text_corpus"]
    assert "图表显示空气质量持续改善" in doc["text_corpus"]
    kinds = {str(item.get("kind") or "") for item in doc["source_texts"]}
    assert "assistant1_markdown" in kinds
    assert "assistant_payload" in kinds
    assert "markdown" in kinds


def test_module4_sync_outbox_runtime_text_corpus_only_mode_compacts_documents() -> None:
    documents = [
        {
            "file_name": "compact.pdf",
            "file_hash": "hash-compact",
            "track": "VisualTrack",
            "result": {"金额": {"value": "1000"}},
            "trace_hits": [{"snippet": "金额合计为1000元"}],
            "diagnostics": {"assistant1_source_markdown_artifact_path": "assistant_1_source/demo.md"},
            "errors": ["legacy error"],
            "soft_warnings": ["legacy warning"],
        }
    ]

    normalized = Module4SyncOutboxRuntime.normalize_documents(documents, payload_mode="text_corpus_only")
    assert len(normalized) == 1
    doc = normalized[0]
    assert set(doc.keys()) == {
        "file_name",
        "file_hash",
        "track",
        "cached",
        "text_corpus",
        "source_texts",
        "settings_overrides",
        "metadata",
        "diagnostics",
    }
    assert "金额合计为1000元" in doc["text_corpus"]
    assert any(item.get("kind") == "assistant1_markdown" for item in doc["source_texts"])


def test_module4_sync_outbox_runtime_recover_pending_outbox_schedules_valid_rows() -> None:
    logger = _FakeLogger()
    metrics = _FakeMetricsRuntime()
    storage = _RecoverStorage()
    runtime = _build_runtime(
        outbox_repository=storage,
        metrics_runtime=metrics,
        logger=logger,
        transport=lambda url, headers, data, timeout_sec: asyncio.sleep(0, result=(200, "{}")),
    )
    scheduled: list[str] = []

    async def _run() -> int:
        return await runtime.recover_pending_outbox(schedule_outbox=scheduled.append, limit=77)

    recovered = asyncio.run(_run())

    assert recovered == 2
    assert scheduled == ["outbox-r1", "outbox-r2"]
    assert storage.limits == [77]


def test_module4_sync_outbox_runtime_builds_list_response_with_metrics() -> None:
    rows = [
        {
            "outbox_id": "outbox-list-1",
            "tenant_id": "tenant-list",
            "source": "module2",
            "source_batch_key": "batch-list",
            "endpoint": "/module4/ingest",
            "sync_kind": "document_batch",
            "file_hash": "file-list",
            "status": "queued",
            "attempt_count": 1,
            "max_attempts": 2,
            "last_error": "",
            "next_attempt_at": None,
            "last_attempt_at": None,
            "delivered_at": None,
            "created_at": None,
            "updated_at": None,
            "payload_json": {"tenant_id": "tenant-list", "source": "module2", "documents": []},
            "last_response_json": {},
        }
    ]

    response = Module4SyncOutboxRuntime.list_response(
        rows=rows,
        tenant_id=" tenant-list ",
        source=" module2 ",
        source_batch_key=" batch-list ",
        endpoint=" /module4/ingest ",
        statuses=["queued", "failed"],
        limit=25,
        include_payload=False,
        include_future=True,
        metrics_snapshot={
            "attempted_batches": 3,
            "succeeded_batches": 2,
            "failed_batches": 1,
            "last_error": "boom",
            "last_job_id": "job-9",
            "last_batch_id": "batch-9",
            "last_endpoint": "/module4/ingest",
            "last_source_batch_key": "batch-list",
        },
    )

    assert response["count"] == 1
    assert response["items"][0]["outbox_id"] == "outbox-list-1"
    assert response["filters"] == {
        "tenant_id": "tenant-list",
        "source": "module2",
        "source_batch_key": "batch-list",
        "endpoint": "/module4/ingest",
        "status": ["queued", "failed"],
        "limit": 25,
        "include_payload": False,
        "include_future": True,
    }
    assert response["metrics"] == {
        "attempted_batches": 3,
        "succeeded_batches": 2,
        "failed_batches": 1,
        "last_error": "boom",
        "last_job_id": "job-9",
        "last_batch_id": "batch-9",
        "last_endpoint": "/module4/ingest",
        "last_source_batch_key": "batch-list",
    }


def test_module4_sync_outbox_runtime_rejects_removed_storage_compat_param() -> None:
    logger = _FakeLogger()
    metrics = _FakeMetricsRuntime()
    storage = _SuccessStorage()
    with pytest.raises(TypeError):
        Module4SyncOutboxRuntime(
            logger=logger,
            storage=storage,
            metrics_runtime=metrics,
            base_url_factory=lambda: "https://module4.example",
            headers_factory=lambda tenant_id: {"X-Tenant-Id": tenant_id},
            timeout_factory=lambda: 12.0,
            retries_factory=lambda: 1,
            retryable_status=lambda status_code: status_code in {500},
            delay_factory=lambda attempt_index: 0.0,
            utcnow_factory=lambda: datetime.now(timezone.utc),
            default_tenant_factory=lambda: "default",
            transport=lambda url, headers, data, timeout_sec: asyncio.sleep(0, result=(200, "{}")),
            sleep_fn=lambda seconds: asyncio.sleep(0),
        )
