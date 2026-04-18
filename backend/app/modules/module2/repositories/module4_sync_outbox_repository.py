from __future__ import annotations

from datetime import datetime
import warnings
from typing import Any, Dict, List, Optional


class Module4SyncOutboxRepository:
    """Repository wrapper for module4 sync outbox persistence operations."""

    def __init__(self, *, storage: Any | None = None) -> None:
        if storage is None:
            raise ValueError("storage is required")
        self._storage = storage

    @property
    def legacy_storage(self) -> Any:
        warnings.warn(
            "Module4SyncOutboxRepository.legacy_storage is deprecated; use Module4SyncOutboxRepository.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._storage

    @property
    def storage(self) -> Any:
        return self._storage

    async def upsert_graph_sync_outbox(
        self,
        *,
        tenant_id: str,
        source: str,
        source_batch_key: str,
        endpoint: str,
        payload: Dict[str, Any],
        sync_kind: str = "document_batch",
        file_hash: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Optional[Dict[str, Any]]:
        return await self._storage.upsert_graph_sync_outbox(
            tenant_id=tenant_id,
            source=source,
            source_batch_key=source_batch_key,
            endpoint=endpoint,
            payload=payload,
            sync_kind=sync_kind,
            file_hash=file_hash,
            max_attempts=max_attempts,
        )

    async def get_graph_sync_outbox(self, outbox_id: str) -> Optional[Dict[str, Any]]:
        return await self._storage.get_graph_sync_outbox(outbox_id)

    async def list_graph_sync_outbox(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return await self._storage.list_graph_sync_outbox(**kwargs)

    async def claim_graph_sync_outbox(self, outbox_id: str) -> Optional[Dict[str, Any]]:
        return await self._storage.claim_graph_sync_outbox(outbox_id)

    async def mark_graph_sync_outbox_delivered(
        self,
        *,
        outbox_id: str,
        response_payload: Dict[str, Any],
    ) -> None:
        await self._storage.mark_graph_sync_outbox_delivered(
            outbox_id=outbox_id,
            response_payload=response_payload,
        )

    async def requeue_graph_sync_outbox(
        self,
        *,
        outbox_id: str,
        error_message: str,
        next_attempt_at: datetime,
    ) -> None:
        await self._storage.requeue_graph_sync_outbox(
            outbox_id=outbox_id,
            error_message=error_message,
            next_attempt_at=next_attempt_at,
        )

    async def mark_graph_sync_outbox_failed(self, *, outbox_id: str, error_message: str) -> None:
        await self._storage.mark_graph_sync_outbox_failed(
            outbox_id=outbox_id,
            error_message=error_message,
        )

    async def recover_pending_graph_sync_outbox(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        return await self._storage.recover_pending_graph_sync_outbox(limit=limit)
