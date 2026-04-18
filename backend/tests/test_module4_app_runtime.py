from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


app_runtime_module = import_module("app.modules.module4.core.app_runtime")


def _build_runtime(**overrides):
    storage = overrides.pop("storage", object())
    job_tasks = overrides.pop("job_tasks", {})
    workspace_builder = overrides.pop("workspace_builder", object())
    projector = overrides.pop("neo4j_graph_projector", object())
    indexer = overrides.pop("graphrag_indexer", object())
    query_helpers = overrides.pop("query_helpers", object())
    insight_helpers = overrides.pop("insight_helpers", object())
    ingest_helpers = overrides.pop("ingest_helpers", object())
    logger = overrides.pop("logger", object())

    return app_runtime_module.Module4AppRuntime(
        storage_getter=lambda: storage,
        job_tasks_getter=lambda: job_tasks,
        workspace_builder_getter=lambda: workspace_builder,
        neo4j_graph_projector_getter=lambda: projector,
        graphrag_indexer_getter=lambda: indexer,
        ingest_helpers_getter=lambda: ingest_helpers,
        query_helpers_getter=lambda: query_helpers,
        insight_helpers_getter=lambda: insight_helpers,
        logger=logger,
        **overrides,
    )


def test_module4_app_runtime_build_router_deps_kwargs_uses_runtime_getters() -> None:
    storage = object()
    workspace_builder = object()
    projector = object()
    indexer = object()
    query_helpers = SimpleNamespace(name="query")
    insight_helpers = SimpleNamespace(name="insight")

    async def _submit_ingest_job(*_args, **_kwargs):
        return {"ok": True}

    def _schedule_rebuild_job(job_id: str, payload: object) -> None:
        del job_id, payload

    runtime = _build_runtime(
        storage=storage,
        workspace_builder=workspace_builder,
        neo4j_graph_projector=projector,
        graphrag_indexer=indexer,
        query_helpers=query_helpers,
        insight_helpers=insight_helpers,
    )

    kwargs = runtime.build_router_deps_kwargs(
        submit_ingest_job=_submit_ingest_job,
        schedule_rebuild_job=_schedule_rebuild_job,
    )

    assert kwargs["storage_getter"]() is storage
    assert kwargs["workspace_builder_getter"]() is workspace_builder
    assert kwargs["neo4j_graph_projector_getter"]() is projector
    assert kwargs["graphrag_indexer_getter"]() is indexer
    assert kwargs["query_helpers"] is query_helpers
    assert kwargs["insight_helpers"] is insight_helpers
    assert kwargs["submit_ingest_job"] is _submit_ingest_job
    assert kwargs["schedule_rebuild_job"] is _schedule_rebuild_job
    assert callable(kwargs["tenant_from_request"])
    assert callable(kwargs["validate_internal_request"])
    assert callable(kwargs["parse_csv_list"])
    assert callable(kwargs["now_utc"])


def test_module4_app_runtime_submit_ingest_job_maps_value_error_to_http_400() -> None:
    captured: dict[str, object] = {}

    async def _submit_ingest_job_fn(**kwargs):
        captured.update(kwargs)
        raise ValueError("documents payload is required")

    runtime = _build_runtime(
        submit_ingest_job_fn=_submit_ingest_job_fn,
        tenant_from_request_fn=lambda request, candidate=None: str(candidate or request.headers.get("x-tenant-id") or ""),
    )

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/module4/ingest",
        "headers": [(b"x-tenant-id", b"tenant-from-header")],
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            runtime.submit_ingest_job(
                SimpleNamespace(tenant_id="", source="module2", documents=[{"file_name": "demo.pdf"}]),
                request,
            )
        )

    assert exc_info.value.status_code == 400
    assert "documents payload is required" in str(exc_info.value.detail)
    assert captured["tenant_id"] == "tenant-from-header"
