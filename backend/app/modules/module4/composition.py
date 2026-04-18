from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from app.modules.module4.api.router import router as module4_router
from app.modules.module4.core.application import (
    lifespan as module4_lifespan,
    module4_app_runtime,
)
from app.modules.module4.schemas import GraphRAGRuntimeStatus, HealthzResponse
from app.modules.module4.services.query.runtime import (
    projection_runtime_status as projection_runtime_status_service,
)


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(module4_router)
    return router


def embedded_lifespan(app: Any):
    return module4_lifespan(app)


async def build_health_payload(probe: str = "basic") -> dict[str, Any]:
    storage = module4_app_runtime.storage_getter()
    workspace_builder = module4_app_runtime.workspace_builder_getter()
    graphrag_indexer = module4_app_runtime.graphrag_indexer_getter()
    neo4j_graph_projector = module4_app_runtime.neo4j_graph_projector_getter()
    diag = storage.diagnostics()

    probe_mode = str(probe or "").strip().lower() or "basic"
    check_remote = probe_mode == "deep"
    queue_size = 0
    health_errors: list[str] = []

    try:
        queue_size = int(await asyncio.wait_for(storage.queue_size(), timeout=2.0))
    except Exception as exc:
        queue_size = 0
        health_errors.append(f"queue_size_check_failed: {type(exc).__name__}")

    runtime_probe_timeout = 15.0 if check_remote else 2.5
    try:
        runtime_probe = await asyncio.wait_for(
            asyncio.to_thread(
                graphrag_indexer.probe,
                workspace_builder.runtime,
                workspace_builder.neo4j,
                check_remote=check_remote,
            ),
            timeout=runtime_probe_timeout,
        )
        graphrag_payload = runtime_probe.as_dict()
    except asyncio.TimeoutError:
        health_errors.append(f"graphrag_probe_timeout_{runtime_probe_timeout:.1f}s")
        graphrag_payload = GraphRAGRuntimeStatus(
            ready=False,
            check_mode="deep" if check_remote else "basic",
            module_error_message=f"GraphRAG runtime probe timeout after {runtime_probe_timeout:.1f}s",
        ).model_dump(mode="python")
    except Exception as exc:
        health_errors.append(f"graphrag_probe_failed: {type(exc).__name__}")
        graphrag_payload = GraphRAGRuntimeStatus(
            ready=False,
            check_mode="deep" if check_remote else "basic",
            module_error_message=f"{type(exc).__name__}: {exc}",
        ).model_dump(mode="python")

    last_connect_error_parts = [str(diag.get("last_connect_error") or "").strip(), *health_errors]
    last_connect_error = " | ".join(part for part in last_connect_error_parts if part) or None

    return HealthzResponse(
        status="ok" if bool(diag.get("db_connected")) else "failed",
        db_connected=bool(diag.get("db_connected")),
        jobs_in_queue=queue_size,
        last_connect_error=last_connect_error,
        graphrag=graphrag_payload,
        projection_runtime=projection_runtime_status_service(
            workspace_builder=workspace_builder,
            neo4j_graph_projector=neo4j_graph_projector,
        ),
        now=module4_app_runtime.now_utc(),
    ).model_dump(mode="python")


router = build_router()

__all__ = ["build_health_payload", "build_router", "embedded_lifespan", "router"]
