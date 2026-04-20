from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional


ScheduleOutboxFn = Callable[[str], None]
EnqueueDocumentSyncFn = Callable[..., Awaitable[Dict[str, Any] | None]]
EnqueueDocumentSyncForSeedFn = Callable[..., Awaitable[bool]]
PrepareDocumentSyncForSeedFn = Callable[..., Awaitable[Dict[str, Any] | None]]
DeliverPreparedOutboxFn = Callable[[str], Awaitable[None]]
ListOutboxRowsFn = Callable[..., Awaitable[List[Dict[str, Any]]]]
GetOutboxRowFn = Callable[[str], Awaitable[Dict[str, Any] | None]]
ListResponseFn = Callable[..., Dict[str, Any]]
SerializeOutboxRowFn = Callable[..., Dict[str, Any]]
MetricsSnapshotFn = Callable[[], Dict[str, Any]]
SourceBatchKeyFn = Callable[..., str]
DocumentSyncMode = Literal["default", "per_file", "final_batch"]


@dataclass(frozen=True)
class SyncCallbackBundle:
    schedule_outbox: ScheduleOutboxFn
    source_batch_key: SourceBatchKeyFn
    enqueue_document_sync: EnqueueDocumentSyncFn
    enqueue_document_sync_for_seed: EnqueueDocumentSyncForSeedFn
    prepare_document_sync_for_seed: PrepareDocumentSyncForSeedFn
    deliver_prepared_outbox: DeliverPreparedOutboxFn
    list_outbox_rows: ListOutboxRowsFn
    get_outbox_row: GetOutboxRowFn
    build_list_response: ListResponseFn
    serialize_outbox_row: SerializeOutboxRowFn
    metrics_snapshot: MetricsSnapshotFn


def build_sync_callback_bundle(
    *,
    outbox_repository: Any,
    module4_sync_config_runtime,
    module4_sync_outbox_runtime,
    module4_sync_task_runtime,
    module4_sync_metrics_runtime,
) -> SyncCallbackBundle:
    if outbox_repository is None:
        raise ValueError("outbox_repository is required")

    def _schedule_outbox(outbox_id: str) -> None:
        key = str(outbox_id or "").strip()
        if not key or not module4_sync_config_runtime.sync_enabled():
            return
        initial_delay_sec = float(module4_sync_config_runtime.initial_dispatch_delay_sec() or 0.0)

        async def _deliver() -> None:
            if initial_delay_sec > 0:
                await asyncio.sleep(initial_delay_sec)
            await module4_sync_outbox_runtime.deliver_outbox(key)

        module4_sync_task_runtime.schedule_indexed(
            outbox_id=key,
            task_factory=lambda: asyncio.create_task(
                _deliver(),
            ),
        )

    def _source_batch_key(*, source: str, tenant_id: str, documents: List[Any], seed: str) -> str:
        return module4_sync_outbox_runtime.source_batch_key(
            source=source,
            tenant_id=tenant_id,
            documents=documents,
            seed=seed,
            payload_mode=module4_sync_config_runtime.payload_mode(),
        )

    async def _enqueue_document_sync(
        *,
        source: str,
        tenant_id: str,
        documents: List[Any],
        source_batch_key: str,
        schedule_immediately: bool = True,
    ) -> Dict[str, Any] | None:
        if not module4_sync_config_runtime.document_sync_enabled():
            return None
        row = await module4_sync_outbox_runtime.enqueue_document_sync(
            source=source,
            tenant_id=tenant_id,
            documents=documents,
            source_batch_key=source_batch_key,
            payload_mode=module4_sync_config_runtime.payload_mode(),
            schedule_outbox=_schedule_outbox if schedule_immediately else (lambda _outbox_id: None),
        )
        return dict(row) if isinstance(row, dict) else row

    async def _enqueue_document_sync_for_seed(
        *,
        source: str,
        tenant_id: str,
        documents: List[Any],
        seed: str,
        mode: DocumentSyncMode = "default",
        schedule_immediately: bool = True,
    ) -> bool:
        if not module4_sync_config_runtime.document_sync_enabled():
            return False
        normalized_mode = str(mode or "default").strip().lower() or "default"
        if normalized_mode == "per_file" and not module4_sync_config_runtime.document_sync_per_file_enabled():
            return False
        if normalized_mode == "final_batch" and not module4_sync_config_runtime.document_sync_final_batch_enabled():
            return False
        row = await _enqueue_document_sync(
            source=source,
            tenant_id=tenant_id,
            documents=documents,
            source_batch_key=_source_batch_key(
                source=source,
                tenant_id=tenant_id,
                documents=documents,
                seed=seed,
            ),
            schedule_immediately=schedule_immediately,
        )
        return row is not None

    async def _prepare_document_sync_for_seed(
        *,
        source: str,
        tenant_id: str,
        documents: List[Any],
        seed: str,
        mode: DocumentSyncMode = "default",
    ) -> Dict[str, Any] | None:
        if not module4_sync_config_runtime.document_sync_enabled():
            return None
        normalized_mode = str(mode or "default").strip().lower() or "default"
        if normalized_mode == "per_file" and not module4_sync_config_runtime.document_sync_per_file_enabled():
            return None
        if normalized_mode == "final_batch" and not module4_sync_config_runtime.document_sync_final_batch_enabled():
            return None
        return await _enqueue_document_sync(
            source=source,
            tenant_id=tenant_id,
            documents=documents,
            source_batch_key=_source_batch_key(
                source=source,
                tenant_id=tenant_id,
                documents=documents,
                seed=seed,
            ),
            schedule_immediately=False,
        )

    async def _deliver_prepared_outbox(outbox_id: str) -> None:
        key = str(outbox_id or "").strip()
        if not key or not module4_sync_config_runtime.sync_enabled():
            return
        await module4_sync_outbox_runtime.deliver_outbox(key)

    async def _list_outbox_rows(**kwargs) -> List[Dict[str, Any]]:
        return await outbox_repository.list_graph_sync_outbox(**kwargs)

    async def _get_outbox_row(outbox_id: str) -> Optional[Dict[str, Any]]:
        return await outbox_repository.get_graph_sync_outbox(outbox_id)

    def _build_list_response(**kwargs) -> Dict[str, Any]:
        return module4_sync_outbox_runtime.list_response(**kwargs)

    def _serialize_outbox_row(row, *, include_payload: bool = False) -> Dict[str, Any]:
        return module4_sync_outbox_runtime.serialize_outbox_row(
            row,
            include_payload=include_payload,
        )

    def _metrics_snapshot() -> Dict[str, Any]:
        return module4_sync_metrics_runtime.snapshot()

    return SyncCallbackBundle(
        schedule_outbox=_schedule_outbox,
        source_batch_key=_source_batch_key,
        enqueue_document_sync=_enqueue_document_sync,
        enqueue_document_sync_for_seed=_enqueue_document_sync_for_seed,
        prepare_document_sync_for_seed=_prepare_document_sync_for_seed,
        deliver_prepared_outbox=_deliver_prepared_outbox,
        list_outbox_rows=_list_outbox_rows,
        get_outbox_row=_get_outbox_row,
        build_list_response=_build_list_response,
        serialize_outbox_row=_serialize_outbox_row,
        metrics_snapshot=_metrics_snapshot,
    )


# Backward-compatible aliases retained for legacy imports.
Module4SyncCallbackBundle = SyncCallbackBundle


def build_module4_sync_callback_bundle(
    *,
    outbox_repository: Any,
    module4_sync_config_runtime=None,
    module4_sync_outbox_runtime=None,
    module4_sync_task_runtime=None,
    module4_sync_metrics_runtime=None,
) -> Module4SyncCallbackBundle:
    return build_sync_callback_bundle(
        outbox_repository=outbox_repository,
        module4_sync_config_runtime=module4_sync_config_runtime,
        module4_sync_outbox_runtime=module4_sync_outbox_runtime,
        module4_sync_task_runtime=module4_sync_task_runtime,
        module4_sync_metrics_runtime=module4_sync_metrics_runtime,
    )


__all__ = [
    "SyncCallbackBundle",
    "Module4SyncCallbackBundle",
    "build_sync_callback_bundle",
    "build_module4_sync_callback_bundle",
]
