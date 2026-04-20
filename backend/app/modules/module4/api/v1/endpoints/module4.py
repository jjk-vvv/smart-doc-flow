from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ...deps import Module4RouterDeps
from ....schemas import (
    AlertActionRequest,
    AlertActionResponse,
    AlertListResponse,
    AlertResolveRequest,
    EvidenceListResponse,
    ExplainRequest,
    ExplainResponse,
    GraphFileDetailResponse,
    GraphFileListResponse,
    GraphNodeDetailResponse,
    GraphRAGQueryRequest,
    GraphRAGQueryResponse,
    GraphResponse,
    GraphRAGRuntimeStatus,
    HealthzResponse,
    IngestRequest,
    IngestResponse,
    JobResponse,
    RebuildRequest,
    RebuildResponse,
    RuleListResponse,
    RuleUpsertRequest,
    RuleUpsertResponse,
    SimulateRequest,
    SimulateResponse,
)
from ....services.graphrag.query_service import (
    GraphRAGQueryServiceError,
    search_graph as graphrag_query_response_service,
)
from ....services.ingestion.runtime import (
    refresh_running_job_progress_from_logs as refresh_running_job_progress_from_logs_service,
    submit_rebuild_job as submit_rebuild_job_service,
)
from ....services.insights.runtime import (
    explain_response as explain_response_service,
    simulate_response as simulate_response_service,
)
from ....services.query.runtime import (
    augment_graphrag_query_payload_with_file_assets as augment_graphrag_query_payload_with_file_assets_service,
    alert_action_response as alert_action_response_service,
    alerts_response as alerts_response_service,
    edge_evidence_response as edge_evidence_response_service,
    evidence_response as evidence_response_service,
    graph_file_detail_response as graph_file_detail_response_service,
    graph_file_neighborhood_response as graph_file_neighborhood_response_service,
    graph_file_node_detail_response as graph_file_node_detail_response_service,
    graph_file_view_response as graph_file_view_response_service,
    graph_response as graph_response_service,
    list_graph_files_response as list_graph_files_response_service,
    neighborhood_response as neighborhood_response_service,
    projection_runtime_status as projection_runtime_status_service,
    rule_upsert_response as rule_upsert_response_service,
    rules_response as rules_response_service,
)

_STATUS_ONLY_RESULT_KEYS = (
    "stage",
    "failure_stage",
    "failure_category",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _build_job_response_payload(row: dict[str, Any], *, status_only: bool) -> JobResponse:
    if not status_only:
        return JobResponse(**row)

    raw_result = _as_dict(row.get("result"))
    trimmed_result = {
        key: raw_result.get(key)
        for key in _STATUS_ONLY_RESULT_KEYS
        if raw_result.get(key) not in (None, "", [], {})
    }
    payload = dict(row)
    payload["payload"] = {}
    payload["result"] = trimmed_result
    return JobResponse(**payload)


def build_router(*, deps: Module4RouterDeps) -> APIRouter:
    async def _require_internal_request(request: Request) -> None:
        deps.validate_internal_request(request)

    router = APIRouter(
        prefix="/module4",
        tags=["module4"],
        dependencies=[Depends(_require_internal_request)],
    )

    @router.post("/ingest", response_model=IngestResponse)
    async def module4_ingest(payload: IngestRequest, request: Request) -> IngestResponse:
        return await deps.submit_ingest_job(payload, request)

    @router.get("/jobs/{job_id}", response_model=JobResponse)
    async def module4_job_status(
        job_id: str,
        request: Request,
        tenant_id: str = Query(default=""),
        status_only: bool = Query(default=False),
    ) -> JobResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        row = await deps.storage_getter().get_job(job_id, tenant_id=resolved_tenant)
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        row = await refresh_running_job_progress_from_logs_service(
            storage=deps.storage_getter(),
            row=row,
        )
        return _build_job_response_payload(row, status_only=status_only)

    @router.post("/rebuild", response_model=RebuildResponse)
    async def module4_rebuild(body: RebuildRequest, request: Request) -> RebuildResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        storage = deps.storage_getter()
        batches = await storage.list_ingest_batches(tenant_id=tenant_id)
        if not batches:
            raise HTTPException(status_code=404, detail="No ingest batches found for tenant")

        payload = await submit_rebuild_job_service(
            storage=storage,
            tenant_id=tenant_id,
            schedule_rebuild_job=deps.schedule_rebuild_job,
        )
        return RebuildResponse(
            job_id=str(payload["job_id"]),
            status=str(payload["status"]),
            batches=int(payload["batches"]),
            documents=int(payload["documents"]),
        )

    @router.get("/graph/files", response_model=GraphFileListResponse)
    async def module4_graph_files(
        request: Request,
        tenant_id: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = 200,
    ) -> GraphFileListResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await list_graph_files_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            status=status,
            limit=limit,
        )

    @router.get("/graph/files/{file_hash}", response_model=GraphFileDetailResponse)
    async def module4_graph_file_detail(
        file_hash: str,
        request: Request,
        tenant_id: str = Query(default=""),
    ) -> GraphFileDetailResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await graph_file_detail_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            file_hash=file_hash,
        )

    @router.get("/graph/files/{file_hash}/view", response_model=GraphResponse)
    async def module4_graph_file_view(
        file_hash: str,
        request: Request,
        tenant_id: str = Query(default=""),
        node_types: str = "",
        relation_types: str = "",
        limit_nodes: int = 800,
        limit_edges: int = 1500,
    ) -> GraphResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await graph_file_view_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            file_hash=file_hash,
            node_types=deps.parse_csv_list(node_types),
            relation_types=deps.parse_csv_list(relation_types),
            limit_nodes=limit_nodes,
            limit_edges=limit_edges,
        )

    @router.post("/query/search", response_model=GraphRAGQueryResponse)
    async def module4_query_search(body: GraphRAGQueryRequest, request: Request) -> GraphRAGQueryResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        try:
            payload = await graphrag_query_response_service(
                storage=deps.storage_getter(),
                tenant_id=tenant_id,
                file_hash=body.file_hash,
                query=body.query,
                mode=body.mode,
                response_type=body.response_type,
                community_level=body.community_level,
                dynamic_community_selection=body.dynamic_community_selection,
                verbose=body.verbose,
            )
        except GraphRAGQueryServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        payload = augment_graphrag_query_payload_with_file_assets_service(
            helpers=deps.query_helpers,
            payload=payload,
            tenant_id=tenant_id,
        )
        return GraphRAGQueryResponse(**payload)

    @router.get("/graph/files/{file_hash}/neighborhood/{node_id}", response_model=GraphResponse)
    async def module4_graph_file_neighborhood(
        file_hash: str,
        node_id: str,
        request: Request,
        tenant_id: str = Query(default=""),
        depth: int = 1,
        relation_types: str = "",
        limit: int = 1200,
    ) -> GraphResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await graph_file_neighborhood_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            file_hash=file_hash,
            node_id=node_id,
            depth=depth,
            relation_types=deps.parse_csv_list(relation_types),
            limit=limit,
        )

    @router.get("/graph/files/{file_hash}/node/{node_id}", response_model=GraphNodeDetailResponse)
    async def module4_graph_file_node_detail(
        file_hash: str,
        node_id: str,
        request: Request,
        tenant_id: str = Query(default=""),
        depth: int = 1,
        relation_types: str = "",
        limit: int = 240,
    ) -> GraphNodeDetailResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await graph_file_node_detail_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            file_hash=file_hash,
            node_id=node_id,
            depth=depth,
            relation_types=deps.parse_csv_list(relation_types),
            limit=limit,
        )

    @router.get("/graph", response_model=GraphResponse)
    async def module4_graph(
        request: Request,
        tenant_id: str = Query(default=""),
        node_types: str = "",
        relation_types: str = "",
        limit_nodes: int = 800,
        limit_edges: int = 1500,
    ) -> GraphResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await graph_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            node_types=deps.parse_csv_list(node_types),
            relation_types=deps.parse_csv_list(relation_types),
            limit_nodes=limit_nodes,
            limit_edges=limit_edges,
        )

    @router.get("/graph/neighborhood/{node_id}", response_model=GraphResponse)
    async def module4_neighborhood(
        node_id: str,
        request: Request,
        tenant_id: str = Query(default=""),
        depth: int = 1,
        relation_types: str = "",
        limit: int = 1200,
    ) -> GraphResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await neighborhood_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            node_id=node_id,
            depth=depth,
            relation_types=deps.parse_csv_list(relation_types),
            limit=limit,
        )

    @router.get("/alerts", response_model=AlertListResponse)
    async def module4_alerts(
        request: Request,
        tenant_id: str = Query(default=""),
        status: Optional[str] = None,
        severity: Optional[str] = None,
        rule_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AlertListResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await alerts_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            status=status,
            severity=severity,
            rule_id=rule_id,
            page=page,
            page_size=page_size,
        )

    @router.post("/alerts/{alert_id}/ack", response_model=AlertActionResponse)
    async def module4_alert_ack(alert_id: str, body: AlertActionRequest, request: Request) -> AlertActionResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        return await alert_action_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            alert_id=alert_id,
            tenant_id=tenant_id,
            status="ack",
            actor=body.actor,
            comment=body.comment,
        )

    @router.post("/alerts/{alert_id}/resolve", response_model=AlertActionResponse)
    async def module4_alert_resolve(
        alert_id: str,
        body: AlertResolveRequest,
        request: Request,
    ) -> AlertActionResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        return await alert_action_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            alert_id=alert_id,
            tenant_id=tenant_id,
            status="resolved",
            actor=body.actor,
            comment=body.comment,
            resolution=body.resolution,
        )

    @router.get("/evidence", response_model=EvidenceListResponse)
    async def module4_evidence(
        request: Request,
        tenant_id: str = Query(default=""),
        doc_id: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> EvidenceListResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await evidence_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            doc_id=doc_id,
            object_type=object_type,
            object_id=object_id,
            page=page,
            page_size=page_size,
        )

    @router.get("/evidence/edge/{edge_id}", response_model=EvidenceListResponse)
    async def module4_edge_evidence(
        edge_id: str,
        request: Request,
        tenant_id: str = Query(default=""),
        page: int = 1,
        page_size: int = 50,
    ) -> EvidenceListResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await edge_evidence_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            edge_id=edge_id,
            page=page,
            page_size=page_size,
        )

    @router.get("/rules", response_model=RuleListResponse)
    async def module4_rules(
        request: Request,
        tenant_id: str = Query(default=""),
        enabled_only: bool = False,
    ) -> RuleListResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await rules_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            enabled_only=enabled_only,
        )

    @router.put("/rules/{rule_id}", response_model=RuleUpsertResponse)
    async def module4_rule_upsert(
        rule_id: str,
        body: RuleUpsertRequest,
        request: Request,
        tenant_id: str = Query(default=""),
    ) -> RuleUpsertResponse:
        resolved_tenant = deps.tenant_from_request(request, tenant_id)
        return await rule_upsert_response_service(
            storage=deps.storage_getter(),
            helpers=deps.query_helpers,
            tenant_id=resolved_tenant,
            rule_id=rule_id,
            body=body,
        )

    @router.post("/explain", response_model=ExplainResponse)
    async def module4_explain(body: ExplainRequest, request: Request) -> ExplainResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        return await explain_response_service(
            storage=deps.storage_getter(),
            helpers=deps.insight_helpers,
            tenant_id=tenant_id,
            body=body,
        )

    @router.post("/simulate", response_model=SimulateResponse)
    async def module4_simulate(body: SimulateRequest, request: Request) -> SimulateResponse:
        tenant_id = deps.tenant_from_request(request, body.tenant_id)
        return await simulate_response_service(
            storage=deps.storage_getter(),
            helpers=deps.insight_helpers,
            tenant_id=tenant_id,
            body=body,
        )

    @router.get("/healthz", response_model=HealthzResponse)
    async def module4_healthz(probe: str = Query(default="basic")) -> HealthzResponse:
        storage = deps.storage_getter()
        workspace_builder = deps.workspace_builder_getter()
        graphrag_indexer = deps.graphrag_indexer_getter()
        neo4j_graph_projector = deps.neo4j_graph_projector_getter()
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
            now=deps.now_utc(),
        )

    return router
