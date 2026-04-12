from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import Request

from ..schemas import IngestRequest, IngestResponse, RebuildRequest


@dataclass(frozen=True)
class Module4RouterDeps:
    storage_getter: Callable[[], Any]
    query_helpers: Any
    insight_helpers: Any
    workspace_builder_getter: Callable[[], Any]
    neo4j_graph_projector_getter: Callable[[], Any]
    graphrag_indexer_getter: Callable[[], Any]
    tenant_from_request: Callable[[Optional[Request], Optional[str]], str]
    parse_csv_list: Callable[[Optional[str]], list[str]]
    submit_ingest_job: Callable[[IngestRequest, Request], Awaitable[IngestResponse]]
    schedule_rebuild_job: Callable[[str, RebuildRequest], None]
    now_utc: Callable[[], Any]


__all__ = ["Module4RouterDeps"]
