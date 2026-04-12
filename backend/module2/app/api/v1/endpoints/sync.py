from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from fastapi import APIRouter, HTTPException, Query


ListOutboxRowsFn = Callable[..., Awaitable[List[Dict[str, Any]]]]
GetOutboxRowFn = Callable[[str], Awaitable[Dict[str, Any] | None]]
ListResponseFn = Callable[..., Dict[str, Any]]
SerializeRowFn = Callable[..., Dict[str, Any]]
MetricsSnapshotFn = Callable[[], Dict[str, Any]]


def build_router(
    *,
    list_outbox_rows: ListOutboxRowsFn,
    get_outbox_row: GetOutboxRowFn,
    build_list_response: ListResponseFn,
    serialize_outbox_row: SerializeRowFn,
    metrics_snapshot: MetricsSnapshotFn,
) -> APIRouter:
    router = APIRouter(tags=["module4-sync"])

    @router.get("/module4-sync/outbox")
    async def module4_sync_outbox_list(
        tenant_id: str = Query(default=""),
        source: str = Query(default="module2"),
        source_batch_key: str = Query(default=""),
        endpoint: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=50, ge=1, le=200),
        include_payload: bool = Query(default=False),
        include_future: bool = Query(default=True),
    ) -> Dict[str, Any]:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        rows = await list_outbox_rows(
            tenant_id=tenant_id or None,
            source=source or None,
            source_batch_key=source_batch_key or None,
            endpoint=endpoint or None,
            statuses=statuses or None,
            limit=limit,
            include_future=include_future,
        )
        return build_list_response(
            rows=rows,
            tenant_id=tenant_id,
            source=source,
            source_batch_key=source_batch_key,
            endpoint=endpoint,
            statuses=statuses,
            limit=limit,
            include_payload=include_payload,
            include_future=include_future,
            metrics_snapshot=metrics_snapshot(),
        )

    @router.get("/module4-sync/outbox/{outbox_id}")
    async def module4_sync_outbox_detail(
        outbox_id: str,
        include_payload: bool = Query(default=True),
    ) -> Dict[str, Any]:
        row = await get_outbox_row(outbox_id)
        if not row:
            raise HTTPException(status_code=404, detail="Module4 sync outbox row not found")
        return serialize_outbox_row(row, include_payload=include_payload)

    return router


__all__ = [
    "ListOutboxRowsFn",
    "GetOutboxRowFn",
    "ListResponseFn",
    "SerializeRowFn",
    "MetricsSnapshotFn",
    "build_router",
]
