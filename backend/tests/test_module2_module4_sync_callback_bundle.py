from __future__ import annotations

import asyncio

import pytest

from app.modules.module2.runtime.module4_sync_callback_bundle import build_module4_sync_callback_bundle


class _FakeStorage:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.detail_calls: list[str] = []

    async def list_graph_sync_outbox(self, **kwargs):
        self.list_calls.append(dict(kwargs))
        return [{"outbox_id": "outbox-1", "status": "queued"}]

    async def get_graph_sync_outbox(self, outbox_id: str):
        self.detail_calls.append(outbox_id)
        return {"outbox_id": outbox_id, "status": "queued"}


class _FakeModule4SyncConfigRuntime:
    def __init__(
        self,
        *,
        sync_enabled: bool,
        document_sync_enabled: bool,
        document_sync_per_file_enabled: bool = True,
        document_sync_final_batch_enabled: bool = False,
    ) -> None:
        self._sync_enabled = sync_enabled
        self._document_sync_enabled = document_sync_enabled
        self._document_sync_per_file_enabled = document_sync_per_file_enabled
        self._document_sync_final_batch_enabled = document_sync_final_batch_enabled
        self._payload_mode = "hybrid"

    def sync_enabled(self) -> bool:
        return self._sync_enabled

    def document_sync_enabled(self) -> bool:
        return self._document_sync_enabled

    def document_sync_per_file_enabled(self) -> bool:
        return self._document_sync_per_file_enabled

    def document_sync_final_batch_enabled(self) -> bool:
        return self._document_sync_final_batch_enabled

    def payload_mode(self) -> str:
        return self._payload_mode


class _FakeModule4SyncOutboxRuntime:
    def __init__(self) -> None:
        self.deliver_calls: list[str] = []
        self.enqueue_calls: list[dict[str, object]] = []
        self.list_response_calls: list[dict[str, object]] = []
        self.serialize_calls: list[dict[str, object]] = []

    async def deliver_outbox(self, outbox_id: str) -> None:
        self.deliver_calls.append(outbox_id)

    async def enqueue_document_sync(self, **kwargs):
        self.enqueue_calls.append(dict(kwargs))
        kwargs["schedule_outbox"]("outbox-queued")
        return {"outbox_id": "outbox-queued"}

    def source_batch_key(self, *, source: str, tenant_id: str, documents, seed: str, payload_mode: str = "hybrid") -> str:
        return f"{source}:{tenant_id}:{seed}:{payload_mode}:{len(list(documents or []))}"

    def list_response(self, **kwargs):
        self.list_response_calls.append(dict(kwargs))
        return {"items": kwargs["rows"], "count": len(kwargs["rows"])}

    def serialize_outbox_row(self, row, *, include_payload: bool = False):
        self.serialize_calls.append({"row": dict(row), "include_payload": include_payload})
        return {"outbox_id": row["outbox_id"], "include_payload": include_payload}


class _FakeModule4SyncTaskRuntime:
    def __init__(self) -> None:
        self.schedule_calls: list[str] = []
        self.tasks: list[asyncio.Task[object]] = []

    def schedule_indexed(self, *, outbox_id: str, task_factory):
        self.schedule_calls.append(outbox_id)
        task = task_factory()
        self.tasks.append(task)
        return task


class _FakeModule4SyncMetricsRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {"attempted_batches": 5}


def test_module4_sync_callback_bundle_orchestrates_schedule_enqueue_and_router_callbacks() -> None:
    storage = _FakeStorage()
    config_runtime = _FakeModule4SyncConfigRuntime(sync_enabled=True, document_sync_enabled=True)
    outbox_runtime = _FakeModule4SyncOutboxRuntime()
    task_runtime = _FakeModule4SyncTaskRuntime()
    metrics_runtime = _FakeModule4SyncMetricsRuntime()

    bundle = build_module4_sync_callback_bundle(
        outbox_repository=storage,
        module4_sync_config_runtime=config_runtime,
        module4_sync_outbox_runtime=outbox_runtime,
        module4_sync_task_runtime=task_runtime,
        module4_sync_metrics_runtime=metrics_runtime,
    )

    async def _scenario() -> None:
        bundle.schedule_outbox("outbox-1")
        await asyncio.gather(*task_runtime.tasks)
        task_runtime.tasks.clear()

        await bundle.enqueue_document_sync(
            source="module2",
            tenant_id="tenant-a",
            documents=[{"file_hash": "file-1"}],
            source_batch_key="batch-1",
        )
        await asyncio.gather(*task_runtime.tasks)

        seeded = await bundle.enqueue_document_sync_for_seed(
            source="module2",
            tenant_id="tenant-a",
            documents=[{"file_hash": "file-2"}],
            seed="seed-1",
            mode="per_file",
        )
        await asyncio.gather(*task_runtime.tasks)

        rows = await bundle.list_outbox_rows(tenant_id="tenant-a", limit=10)
        row = await bundle.get_outbox_row("outbox-1")
        list_payload = bundle.build_list_response(
            rows=rows,
            tenant_id="tenant-a",
            source="module2",
            source_batch_key="batch-1",
            endpoint="",
            statuses=["queued"],
            limit=10,
            include_payload=False,
            include_future=True,
            metrics_snapshot=bundle.metrics_snapshot(),
        )
        detail_payload = bundle.serialize_outbox_row(row, include_payload=True)

        assert list_payload == {"items": [{"outbox_id": "outbox-1", "status": "queued"}], "count": 1}
        assert detail_payload == {"outbox_id": "outbox-1", "include_payload": True}
        assert seeded is True

    asyncio.run(_scenario())

    assert bundle.source_batch_key(
        source="module2",
        tenant_id="tenant-a",
        documents=[{"file_hash": "file-2"}],
        seed="seed-1",
    ) == "module2:tenant-a:seed-1:hybrid:1"
    assert task_runtime.schedule_calls == ["outbox-1", "outbox-queued", "outbox-queued"]
    assert outbox_runtime.deliver_calls == ["outbox-1", "outbox-queued", "outbox-queued"]
    assert outbox_runtime.enqueue_calls and outbox_runtime.enqueue_calls[0]["tenant_id"] == "tenant-a"
    assert outbox_runtime.enqueue_calls[1]["source_batch_key"] == "module2:tenant-a:seed-1:hybrid:1"
    assert storage.list_calls == [{"tenant_id": "tenant-a", "limit": 10}]
    assert storage.detail_calls == ["outbox-1"]
    assert outbox_runtime.list_response_calls and outbox_runtime.list_response_calls[0]["metrics_snapshot"] == {
        "attempted_batches": 5
    }
    assert outbox_runtime.serialize_calls == [
        {
            "row": {"outbox_id": "outbox-1", "status": "queued"},
            "include_payload": True,
        }
    ]
    assert metrics_runtime.calls == 1


def test_module4_sync_callback_bundle_respects_disabled_switches() -> None:
    storage = _FakeStorage()
    config_runtime = _FakeModule4SyncConfigRuntime(
        sync_enabled=False,
        document_sync_enabled=False,
        document_sync_per_file_enabled=False,
        document_sync_final_batch_enabled=False,
    )
    outbox_runtime = _FakeModule4SyncOutboxRuntime()
    task_runtime = _FakeModule4SyncTaskRuntime()
    metrics_runtime = _FakeModule4SyncMetricsRuntime()

    bundle = build_module4_sync_callback_bundle(
        outbox_repository=storage,
        module4_sync_config_runtime=config_runtime,
        module4_sync_outbox_runtime=outbox_runtime,
        module4_sync_task_runtime=task_runtime,
        module4_sync_metrics_runtime=metrics_runtime,
    )

    async def _scenario() -> None:
        bundle.schedule_outbox("outbox-1")
        await bundle.enqueue_document_sync(
            source="module2",
            tenant_id="tenant-a",
            documents=[{"file_hash": "file-1"}],
            source_batch_key="batch-1",
        )
        assert (
            await bundle.enqueue_document_sync_for_seed(
                source="module2",
                tenant_id="tenant-a",
                documents=[{"file_hash": "file-1"}],
                seed="seed-2",
                mode="final_batch",
            )
            is False
        )

    asyncio.run(_scenario())

    assert task_runtime.schedule_calls == []
    assert outbox_runtime.deliver_calls == []
    assert outbox_runtime.enqueue_calls == []


def test_module4_sync_callback_bundle_storage_param_emits_deprecation_warning() -> None:
    storage = _FakeStorage()
    config_runtime = _FakeModule4SyncConfigRuntime(sync_enabled=True, document_sync_enabled=False)
    outbox_runtime = _FakeModule4SyncOutboxRuntime()
    task_runtime = _FakeModule4SyncTaskRuntime()
    metrics_runtime = _FakeModule4SyncMetricsRuntime()

    with pytest.warns(DeprecationWarning):
        build_module4_sync_callback_bundle(
            storage=storage,
            module4_sync_config_runtime=config_runtime,
            module4_sync_outbox_runtime=outbox_runtime,
            module4_sync_task_runtime=task_runtime,
            module4_sync_metrics_runtime=metrics_runtime,
        )
