from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import APIRouter


MODULE4_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE4_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE4_ROOT))

def test_module4_legacy_router_build_emits_deprecation_warning() -> None:
    module = import_module("app.api.compat.router")
    deps = module.Module4RouterDeps(
        storage_getter=lambda: object(),
        query_helpers=object(),
        insight_helpers=object(),
        workspace_builder_getter=lambda: object(),
        neo4j_graph_projector_getter=lambda: object(),
        graphrag_indexer_getter=lambda: object(),
        tenant_from_request=lambda request, tenant_id=None: str(tenant_id or ""),
        parse_csv_list=lambda raw: [item.strip() for item in str(raw or "").split(",") if item.strip()],
        submit_ingest_job=lambda payload, request: None,
        schedule_rebuild_job=lambda job_id, payload: None,
        now_utc=lambda: None,
    )

    with pytest.warns(DeprecationWarning):
        router = module.build_module4_router(deps=deps)

    assert isinstance(router, APIRouter)


def test_module4_root_router_is_thin_compat_shim() -> None:
    root_module = import_module("app.router")
    compat_module = import_module("app.api.compat.router")

    assert root_module.build_module4_router is compat_module.build_module4_router
    assert root_module.graphrag_query_response_service is compat_module.graphrag_query_response_service
