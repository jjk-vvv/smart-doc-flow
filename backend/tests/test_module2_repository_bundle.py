from __future__ import annotations

import asyncio

import pytest

from app.modules.module2.repositories import build_module2_repository_bundle


class _FakeStorage:
    async def connect(self):
        self.connected = True

    async def close(self):
        self.closed = True

    async def clear_runtime_cache(self):
        return {"rows": 3}

    def diagnostics(self):
        return {"db": "ok"}

    async def check_cache(self, cache_key: str):
        return {"cache_key": cache_key}

    async def find_recent_document_caches(self, file_hash: str, *, limit: int = 8):
        return [{"file_hash": file_hash, "limit": limit}]

    async def save_extraction_result(self, cache_key: str, payload):
        self.saved = {"cache_key": cache_key, "payload": dict(payload)}

    async def upsert_graph_sync_outbox(self, **kwargs):
        return {"outbox_id": "outbox-1", **kwargs}

    async def get_graph_sync_outbox(self, outbox_id: str):
        return {"outbox_id": outbox_id}

    async def list_graph_sync_outbox(self, **kwargs):
        return [dict(kwargs)]

    async def claim_graph_sync_outbox(self, outbox_id: str):
        return {"outbox_id": outbox_id, "status": "processing"}

    async def mark_graph_sync_outbox_delivered(self, *, outbox_id: str, response_payload):
        self.delivered = {"outbox_id": outbox_id, "response_payload": dict(response_payload)}

    async def requeue_graph_sync_outbox(self, *, outbox_id: str, error_message: str, next_attempt_at):
        self.requeued = {
            "outbox_id": outbox_id,
            "error_message": error_message,
            "next_attempt_at": next_attempt_at,
        }

    async def mark_graph_sync_outbox_failed(self, *, outbox_id: str, error_message: str):
        self.failed = {"outbox_id": outbox_id, "error_message": error_message}

    async def recover_pending_graph_sync_outbox(self, *, limit: int = 200):
        return [{"outbox_id": "outbox-r", "limit": limit}]


def test_module2_repository_bundle_wraps_storage_interfaces() -> None:
    storage = _FakeStorage()
    bundle = build_module2_repository_bundle(storage=storage)
    assert bundle.storage is storage
    assert bundle.runtime_state_repository.storage is storage
    assert bundle.extraction_cache_repository.storage is storage
    assert bundle.module4_sync_outbox_repository.storage is storage

    with pytest.warns(DeprecationWarning):
        assert bundle.legacy_storage is storage
    with pytest.warns(DeprecationWarning):
        assert bundle.runtime_state_repository.legacy_storage is storage
    with pytest.warns(DeprecationWarning):
        assert bundle.extraction_cache_repository.legacy_storage is storage
    with pytest.warns(DeprecationWarning):
        assert bundle.module4_sync_outbox_repository.legacy_storage is storage

    async def _scenario() -> None:
        await bundle.runtime_state_repository.connect()
        await bundle.runtime_state_repository.close()
        cleared = await bundle.runtime_state_repository.clear_runtime_cache()
        diagnostics = bundle.runtime_state_repository.diagnostics()

        cache_row = await bundle.extraction_cache_repository.check_cache("cache-1")
        recent_rows = await bundle.extraction_cache_repository.find_recent_document_caches("hash-1", limit=3)
        await bundle.extraction_cache_repository.save_extraction_result("cache-1", {"ok": True})

        outbox_row = await bundle.module4_sync_outbox_repository.upsert_graph_sync_outbox(
            tenant_id="tenant-a",
            source="module2",
            source_batch_key="batch-a",
            endpoint="/module4/ingest",
            payload={"k": "v"},
        )
        listed = await bundle.module4_sync_outbox_repository.list_graph_sync_outbox(limit=5)
        detail = await bundle.module4_sync_outbox_repository.get_graph_sync_outbox("outbox-1")
        claimed = await bundle.module4_sync_outbox_repository.claim_graph_sync_outbox("outbox-1")
        recovered = await bundle.module4_sync_outbox_repository.recover_pending_graph_sync_outbox(limit=7)

        assert cleared == {"rows": 3}
        assert diagnostics == {"db": "ok"}
        assert storage.connected is True
        assert storage.closed is True
        assert cache_row == {"cache_key": "cache-1"}
        assert recent_rows == [{"file_hash": "hash-1", "limit": 3}]
        assert storage.saved == {"cache_key": "cache-1", "payload": {"ok": True}}
        assert outbox_row["outbox_id"] == "outbox-1"
        assert listed == [{"limit": 5}]
        assert detail == {"outbox_id": "outbox-1"}
        assert claimed == {"outbox_id": "outbox-1", "status": "processing"}
        assert recovered == [{"outbox_id": "outbox-r", "limit": 7}]

    asyncio.run(_scenario())


def test_module2_repository_bundle_rejects_removed_storage_compat_param() -> None:
    storage = _FakeStorage()
    with pytest.raises(TypeError):
        build_module2_repository_bundle(legacy_storage=storage)
