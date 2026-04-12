from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional


class Module4SyncOutboxRepository:
    """Repository wrapper for module4 sync outbox persistence operations."""

    def __init__(self, *, legacy_storage: Any | None = None, **legacy_kwargs: Any) -> None:
        if "storage" in legacy_kwargs:
            if legacy_storage is not None:
                raise TypeError("Pass only one of legacy_storage=... or storage=...")
            legacy_storage = legacy_kwargs.pop("storage")
            warnings.warn(
                "Module4SyncOutboxRepository(storage=...) is deprecated; "
                "pass legacy_storage=... instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
        if legacy_storage is None:
            raise ValueError("legacy_storage is required")
        self._legacy_storage = legacy_storage

    @property
    def legacy_storage(self) -> Any:
        return self._legacy_storage

    @property
    def storage(self) -> Any:
        warnings.warn(
            "Module4SyncOutboxRepository.storage is deprecated; "
            "use Module4SyncOutboxRepository.legacy_storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._legacy_storage

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
        return await self._legacy_storage.upsert_graph_sync_outbox(
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
        return await self._legacy_storage.get_graph_sync_outbox(outbox_id)

    async def list_graph_sync_outbox(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return await self._legacy_storage.list_graph_sync_outbox(**kwargs)

    async def claim_graph_sync_outbox(self, outbox_id: str) -> Optional[Dict[str, Any]]:
        return await self._legacy_storage.claim_graph_sync_outbox(outbox_id)

    async def mark_graph_sync_outbox_delivered(
        self,
        *,
        outbox_id: str,
        response_payload: Dict[str, Any],
    ) -> None:
        await self._legacy_storage.mark_graph_sync_outbox_delivered(
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
        await self._legacy_storage.requeue_graph_sync_outbox(
            outbox_id=outbox_id,
            error_message=error_message,
            next_attempt_at=next_attempt_at,
        )

    async def mark_graph_sync_outbox_failed(self, *, outbox_id: str, error_message: str) -> None:
        await self._legacy_storage.mark_graph_sync_outbox_failed(
            outbox_id=outbox_id,
            error_message=error_message,
        )

    async def recover_pending_graph_sync_outbox(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        return await self._legacy_storage.recover_pending_graph_sync_outbox(limit=limit)
