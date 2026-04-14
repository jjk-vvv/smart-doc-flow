from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ..api.deps import Module4RouterDeps
from ..api.v1.router import build_api_v1_router
from ..db.storage import Module4Storage
from ..schemas import IngestRequest, IngestResponse, RebuildRequest
from ..services.graphrag.indexer import GraphRAGIndexer
from ..services.graphrag.workspace import GraphRAGWorkspaceBuilder
from ..services.query.neo4j import Neo4jGraphProjector
from .runtime import (
    Module4AppRuntime,
    build_default_composition_components,
    build_insight_runtime_helpers,
    load_module4_env,
    now_utc,
    parse_csv_list,
    tenant_from_request,
)

MODULE4_ROOT = Path(__file__).resolve().parents[1]
load_module4_env(MODULE4_ROOT)
logger = logging.getLogger("uvicorn.error")

_composition_components = build_default_composition_components(
    module4_database_dsn=os.getenv("MODULE4_DATABASE_DSN", "postgresql://postgres:postgres@localhost:5432/a23"),
    storage_factory=Module4Storage,
    workspace_builder_factory=GraphRAGWorkspaceBuilder,
    graphrag_indexer_factory=GraphRAGIndexer,
    neo4j_graph_projector_factory=Neo4jGraphProjector,
)
_runtime_refs: Dict[str, Any] = {
    "storage": _composition_components.storage,
    "job_tasks": _composition_components.job_tasks,
    "workspace_builder": _composition_components.workspace_builder,
    "graphrag_indexer": _composition_components.graphrag_indexer,
    "neo4j_graph_projector": _composition_components.neo4j_graph_projector,
}


def _get_runtime_ref(name: str) -> Any:
    return _runtime_refs[name]


def _set_runtime_ref(name: str, value: Any) -> None:
    _runtime_refs[name] = value


# Keep selected module-level aliases stable because tests patch them directly.
_ingest_runtime_helpers = _composition_components.ingest_helpers
_query_runtime_helpers = _composition_components.query_helpers
_insight_runtime_helpers = build_insight_runtime_helpers(
    storage_getter=lambda: _get_runtime_ref("storage"),
    query_helpers=_query_runtime_helpers,
)

module4_app_runtime = Module4AppRuntime(
    storage_getter=lambda: _get_runtime_ref("storage"),
    job_tasks_getter=lambda: _get_runtime_ref("job_tasks"),
    workspace_builder_getter=lambda: _get_runtime_ref("workspace_builder"),
    neo4j_graph_projector_getter=lambda: _get_runtime_ref("neo4j_graph_projector"),
    graphrag_indexer_getter=lambda: _get_runtime_ref("graphrag_indexer"),
    ingest_helpers_getter=lambda: _ingest_runtime_helpers,
    query_helpers_getter=lambda: _query_runtime_helpers,
    insight_helpers_getter=lambda: _insight_runtime_helpers,
    logger=logger,
    tenant_from_request_fn=tenant_from_request,
    parse_csv_list_fn=parse_csv_list,
    now_utc_fn=now_utc,
)


async def _update_job_stage(
    job_id: str,
    *,
    stage: str,
    progress: float,
    base_result: Optional[Dict[str, Any]] = None,
    **updates: Any,
) -> None:
    await module4_app_runtime.update_job_stage(
        job_id=job_id,
        stage=stage,
        progress=progress,
        base_result=base_result,
        **updates,
    )


async def _recover_jobs() -> None:
    await module4_app_runtime.recover_jobs()


lifespan = module4_app_runtime.build_lifespan(recover_jobs_callback=_recover_jobs)


def _schedule_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
    job_tasks = _get_runtime_ref("job_tasks")
    existing = job_tasks.get(job_id)
    if existing and not existing.done():
        return
    job_tasks[job_id] = asyncio.create_task(_run_ingest_job(job_id, batch_id, payload))


def _schedule_rebuild_job(job_id: str, payload: RebuildRequest) -> None:
    job_tasks = _get_runtime_ref("job_tasks")
    existing = job_tasks.get(job_id)
    if existing and not existing.done():
        return
    job_tasks[job_id] = asyncio.create_task(_run_rebuild_job(job_id, payload))


async def _run_document_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> Dict[str, Any]:
    return await module4_app_runtime.run_document_ingest_job(
        job_id=job_id,
        batch_id=batch_id,
        payload=payload,
        update_job_stage_callback=_update_job_stage,
    )


async def _run_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
    await module4_app_runtime.run_ingest_job(
        job_id=job_id,
        batch_id=batch_id,
        payload=payload,
        run_document_ingest_job_callback=_run_document_ingest_job,
    )


async def _run_rebuild_job(job_id: str, payload: RebuildRequest) -> None:
    await module4_app_runtime.run_rebuild_job(
        job_id=job_id,
        payload=payload,
        run_document_ingest_job_callback=_run_document_ingest_job,
    )


async def _submit_ingest_job(payload: IngestRequest, request: Request) -> IngestResponse:
    return await module4_app_runtime.submit_ingest_job(
        payload,
        request,
        schedule_ingest_job_callback=_schedule_ingest_job,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="A23 Module 4 - Global Knowledge Graph & Risk Intelligence", version="1.1.0", lifespan=lifespan)
    cors_origins_list, cors_allow_all = module4_app_runtime.cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cors_allow_all else cors_origins_list,
        allow_credentials=not cors_allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        build_api_v1_router(
            deps=Module4RouterDeps(
                **module4_app_runtime.build_router_deps_kwargs(
                    submit_ingest_job=_submit_ingest_job,
                    schedule_rebuild_job=_schedule_rebuild_job,
                )
            ),
        )
    )
    return app


app = create_app()
