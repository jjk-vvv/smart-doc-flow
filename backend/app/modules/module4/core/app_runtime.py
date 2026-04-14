from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from ..schemas import IngestRequest, IngestResponse, RebuildRequest

from ..services.ingestion.artifacts import (
    _artifact_display_name_from_attrs,
    _artifact_summary_snippet,
    _as_dict,
    _as_list,
    _normalize_artifact_attrs_for_response,
)
from ..services.ingestion.runtime import (
    Module4IngestRuntimeHelpers,
    RunDocumentIngestJobCallback,
    ScheduleIngestJobCallback,
    ScheduleRebuildJobCallback,
    process_document,
    recover_jobs,
    run_document_ingest_job,
    run_ingest_job,
    run_rebuild_job,
    submit_ingest_job,
    update_job_stage,
)
from ..services.insights.runtime import Module4InsightRuntimeHelpers
from ..services.query.runtime import (
    Module4QueryRuntimeHelpers,
    load_evidence_for_node as load_evidence_for_node_service,
    neighborhood_response as neighborhood_response_service,
    normalize_graph_node_row as normalize_graph_node_row_service,
)
from ..services.ingestion.rules import SUPPORTED_RULE_KINDS, _evaluate_rule_hit, _rule_scope

ALERT_SEVERITY = {"yellow", "orange", "red"}
ALERT_STATUS = {"open", "ack", "resolved", "false_positive"}
EDGE_DIRECTION = {"out", "bi"}
RULE_KIND = {"deterministic"}

StorageGetter = Callable[[], Any]
RecoverJobsCallback = Callable[[], Awaitable[None]]
JobTasksGetter = Callable[[], Dict[str, asyncio.Task[Any]]]
BackgroundCoroutineFactory = Callable[[], Awaitable[Any]]


@dataclass(frozen=True)
class Module4BootstrapComponents:
    storage: Any
    job_tasks: Dict[str, asyncio.Task[Any]]
    workspace_builder: Any
    graphrag_indexer: Any
    neo4j_graph_projector: Any
    ingest_helpers: Module4IngestRuntimeHelpers
    query_helpers: Module4QueryRuntimeHelpers


Module4Components = Module4BootstrapComponents


def load_module4_env(module4_root: Path) -> None:
    load_dotenv(dotenv_path=module4_root / ".env", override=False, interpolate=False)
    custom_module4_env = str(os.getenv("SMART_DOC_FLOW_MODULE4_ENV_FILE", "") or "").strip()
    if custom_module4_env:
        load_dotenv(dotenv_path=custom_module4_env, override=True, interpolate=False)


def cors_origins() -> tuple[list[str], bool]:
    raw = os.getenv("MODULE4_CORS_ORIGINS", "http://localhost:3000,http://localhost:3002,http://localhost:5173")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    allow_all = "*" in origins
    return origins or ["http://localhost:3000"], allow_all


def default_tenant() -> str:
    return os.getenv("MODULE4_DEFAULT_TENANT", "default").strip() or "default"


def module4_tenant_guard_mode() -> str:
    raw_mode = str(os.getenv("MODULE4_TENANT_GUARD_MODE", "compat_default") or "").strip().lower()
    if raw_mode in {"strict", "strict_authenticated_tenant", "authenticated_required"}:
        return "authenticated_required"
    return "compat_default"


def tenant_from_request(request: Optional[Request], candidate: Optional[str] = None) -> str:
    candidate_tenant = str(candidate or "").strip()
    header_tenant = ""
    authenticated_tenant = ""
    authenticated_user = ""
    guard_mode = module4_tenant_guard_mode()
    if request is not None:
        header_tenant = str(request.headers.get("x-tenant-id") or "").strip()
        authenticated_tenant = str(request.headers.get("x-authenticated-tenant-id") or "").strip()
        authenticated_user = str(request.headers.get("x-authenticated-user-id") or "").strip()

    # Prefer authenticated tenant identity when present. Query/body/header tenant candidates
    # become consistency checks and cannot override authenticated ownership.
    authenticated_owner = authenticated_tenant or authenticated_user
    if authenticated_owner:
        if candidate_tenant and candidate_tenant != authenticated_owner:
            raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")
        if header_tenant and header_tenant != authenticated_owner:
            raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")
        return authenticated_owner

    if request is not None and guard_mode == "authenticated_required":
        raise HTTPException(status_code=401, detail="authenticated tenant headers required")

    if candidate_tenant:
        return candidate_tenant
    if header_tenant:
        return header_tenant
    return default_tenant()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_csv_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def risk_key(text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def derived_ingest_batch_key(payload: IngestRequest, tenant_id: Optional[str] = None) -> str:
    if payload.source_batch_key:
        return str(payload.source_batch_key).strip()
    normalized_payload = payload.model_dump(mode="json")
    normalized: Dict[str, Any] = {
        "tenant_id": tenant_id or payload.tenant_id or default_tenant(),
        "source": payload.source,
        "graph_mode": payload.graph_mode,
        "documents": normalized_payload.get("documents", []),
        "text_corpus": normalized_payload.get("text_corpus", ""),
        "source_texts": normalized_payload.get("source_texts", []),
        "settings_overrides": normalized_payload.get("settings_overrides", {}),
        "metadata": normalized_payload.get("metadata", {}),
    }
    return risk_key(stable_json_dumps(normalized))


def build_ingest_runtime_helpers(
    *,
    workspace_builder_getter: Callable[[], Any] | None = None,
    graphrag_indexer_getter: Callable[[], Any] | None = None,
) -> Module4IngestRuntimeHelpers:
    return Module4IngestRuntimeHelpers(
        default_tenant=default_tenant,
        now_utc=now_utc,
        risk_key=risk_key,
        workspace_builder_getter=workspace_builder_getter,
        graphrag_indexer_getter=graphrag_indexer_getter,
    )


def _resolve_module4_query_artifact_path(artifact_reference: str) -> Path | None:
    raw_value = str(artifact_reference or "").strip()
    if not raw_value:
        return None
    lowered = raw_value.lower()
    if lowered.startswith(("http://", "https://", "data:")):
        return None

    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_file():
            return resolved

    # Keep this lazy to avoid importing module2 runtime during startup when unused.
    try:
        from app.core.config import get_settings
        from app.modules.module2.core.artifact_runtime import get_extraction_artifact_runtime
    except Exception:
        return None

    settings = get_settings()
    normalized = raw_value.replace("\\", "/").strip()
    if normalized.startswith("/extract/artifact/"):
        normalized = normalized[len("/extract/artifact/") :]
    elif normalized.startswith("extract/artifact/"):
        normalized = normalized[len("extract/artifact/") :]
    normalized = normalized.lstrip("/\\")

    runtime = get_extraction_artifact_runtime()
    if normalized:
        try:
            resolved = runtime.resolve_existing_artifact_path(settings, normalized)
            if resolved.exists() and resolved.is_file():
                return resolved
        except Exception:
            pass

    if normalized:
        root_candidates = (
            settings.runtime_root_dir.resolve(),
            settings.data_root_dir.resolve(),
            (settings.runtime_root_dir / "backend").resolve(),
        )
        for root in root_candidates:
            try:
                resolved = (root / normalized).resolve()
                resolved.relative_to(root)
            except Exception:
                continue
            if resolved.exists() and resolved.is_file():
                return resolved
    return None


def _register_module4_query_file_asset(
    *,
    path: Path,
    owner_id: str,
    source_module: str,
    purpose: str,
    filename: str | None = None,
) -> Dict[str, Any]:
    from app.modules.file_assets.service import register_file

    return register_file(
        path=path,
        owner_id=owner_id,
        source_module=source_module,
        purpose=purpose,
        filename=filename,
    )


def build_query_runtime_helpers() -> Module4QueryRuntimeHelpers:
    return Module4QueryRuntimeHelpers(
        default_tenant=default_tenant,
        risk_key=risk_key,
        to_float=to_float,
        to_int=to_int,
        as_dict=_as_dict,
        as_list=_as_list,
        artifact_summary_snippet=_artifact_summary_snippet,
        normalize_artifact_attrs_for_response=_normalize_artifact_attrs_for_response,
        artifact_display_name_from_attrs=_artifact_display_name_from_attrs,
        edge_direction=EDGE_DIRECTION,
        alert_severity=ALERT_SEVERITY,
        alert_status=ALERT_STATUS,
        rule_kind=RULE_KIND,
        resolve_artifact_local_path=_resolve_module4_query_artifact_path,
        register_file_asset=_register_module4_query_file_asset,
    )


def build_insight_runtime_helpers(
    *,
    storage_getter: StorageGetter,
    query_helpers: Module4QueryRuntimeHelpers,
) -> Module4InsightRuntimeHelpers:
    def _normalize_graph_node_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_graph_node_row_service(helpers=query_helpers, row=row)

    async def _load_evidence_for_node(tenant_id: str, node_row: Dict[str, Any], *, limit: int = 10) -> List[Dict[str, Any]]:
        return await load_evidence_for_node_service(
            storage=storage_getter(),
            helpers=query_helpers,
            tenant_id=tenant_id,
            node_row=node_row,
            limit=limit,
        )

    async def _load_artifact_neighborhood(
        tenant_id: str,
        node_id: str,
        depth: int = 1,
        limit: int = 40,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        graph = await neighborhood_response_service(
            storage=storage_getter(),
            helpers=query_helpers,
            tenant_id=tenant_id,
            node_id=node_id,
            depth=depth,
            relation_types=[],
            limit=limit,
        )
        nodes = [item.model_dump(mode="python") if hasattr(item, "model_dump") else dict(item) for item in graph.nodes]
        edges = [item.model_dump(mode="python") if hasattr(item, "model_dump") else dict(item) for item in graph.edges]
        return nodes, edges

    return Module4InsightRuntimeHelpers(
        to_float=to_float,
        to_int=to_int,
        as_list=_as_list,
        rule_scope=_rule_scope,
        evaluate_rule_hit=_evaluate_rule_hit,
        normalize_graph_node_row=_normalize_graph_node_row,
        load_evidence_for_node=_load_evidence_for_node,
        load_artifact_neighborhood=_load_artifact_neighborhood,
        supported_rule_kinds=SUPPORTED_RULE_KINDS,
    )


def build_default_components(
    *,
    module4_database_dsn: str,
    storage_factory: Callable[[str], Any],
    workspace_builder_factory: Callable[[], Any],
    graphrag_indexer_factory: Callable[[], Any],
    neo4j_graph_projector_factory: Callable[[Any], Any],
) -> Module4BootstrapComponents:
    storage = storage_factory(module4_database_dsn)
    job_tasks: Dict[str, asyncio.Task[Any]] = {}
    workspace_builder = workspace_builder_factory()
    graphrag_indexer = graphrag_indexer_factory()
    neo4j_graph_projector = neo4j_graph_projector_factory(workspace_builder.neo4j)
    ingest_helpers = build_ingest_runtime_helpers(
        workspace_builder_getter=lambda: workspace_builder,
        graphrag_indexer_getter=lambda: graphrag_indexer,
    )
    query_helpers = build_query_runtime_helpers()
    return Module4BootstrapComponents(
        storage=storage,
        job_tasks=job_tasks,
        workspace_builder=workspace_builder,
        graphrag_indexer=graphrag_indexer,
        neo4j_graph_projector=neo4j_graph_projector,
        ingest_helpers=ingest_helpers,
        query_helpers=query_helpers,
    )


def build_default_bootstrap_components(
    *,
    module4_database_dsn: str,
    storage_factory: Callable[[str], Any],
    workspace_builder_factory: Callable[[], Any],
    graphrag_indexer_factory: Callable[[], Any],
    neo4j_graph_projector_factory: Callable[[Any], Any],
) -> Module4BootstrapComponents:
    """Compatibility alias for historical bootstrap naming."""

    return build_default_components(
        module4_database_dsn=module4_database_dsn,
        storage_factory=storage_factory,
        workspace_builder_factory=workspace_builder_factory,
        graphrag_indexer_factory=graphrag_indexer_factory,
        neo4j_graph_projector_factory=neo4j_graph_projector_factory,
    )


def build_default_composition_components(
    *,
    module4_database_dsn: str,
    storage_factory: Callable[[str], Any],
    workspace_builder_factory: Callable[[], Any],
    graphrag_indexer_factory: Callable[[], Any],
    neo4j_graph_projector_factory: Callable[[Any], Any],
) -> Module4BootstrapComponents:
    """Canonical name for module4 composition assembly."""

    return build_default_components(
        module4_database_dsn=module4_database_dsn,
        storage_factory=storage_factory,
        workspace_builder_factory=workspace_builder_factory,
        graphrag_indexer_factory=graphrag_indexer_factory,
        neo4j_graph_projector_factory=neo4j_graph_projector_factory,
    )


def build_lifespan(
    *,
    storage_getter: StorageGetter,
    job_tasks_getter: JobTasksGetter,
    recover_jobs_callback: RecoverJobsCallback,
    logger: Any,
) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        startup_timeout = max(5.0, to_float(os.getenv("MODULE4_STARTUP_TIMEOUT_SEC"), 20.0))
        recovery_timeout = max(3.0, to_float(os.getenv("MODULE4_RECOVERY_TIMEOUT_SEC"), 8.0))
        logger.info("module4 startup begin")
        storage = storage_getter()
        try:
            await asyncio.wait_for(storage.connect(), timeout=startup_timeout)
            logger.info("module4 storage connect completed: %s", storage.diagnostics())
        except asyncio.TimeoutError as exc:
            logger.error("module4 storage connect timed out after %.1fs", startup_timeout)
            raise RuntimeError(f"module4 storage.connect exceeded {startup_timeout:.1f}s") from exc
        except Exception as exc:
            logger.exception("module4 storage connect failed during startup: %s", exc)
            raise
        try:
            await asyncio.wait_for(recover_jobs_callback(), timeout=recovery_timeout)
            logger.info("module4 job recovery completed")
        except asyncio.TimeoutError:
            logger.warning("module4 job recovery timed out after %.1fs; continuing startup", recovery_timeout)
        except Exception as exc:
            logger.exception("module4 job recovery failed during startup: %s", exc)
        try:
            yield
        finally:
            logger.info("module4 shutdown begin")
            tasks = [task for task in job_tasks_getter().values() if not task.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await storage_getter().close()

    return lifespan


def schedule_background_job(
    *,
    job_tasks_getter: JobTasksGetter,
    job_id: str,
    coroutine_factory: BackgroundCoroutineFactory,
) -> None:
    job_tasks = job_tasks_getter()
    existing = job_tasks.get(job_id)
    if existing and not existing.done():
        return
    job_tasks[job_id] = asyncio.create_task(coroutine_factory())


class Module4AppRuntime:
    """Coordinate Module4 app-level orchestration while keeping `main.py` thin."""

    def __init__(
        self,
        *,
        storage_getter: StorageGetter,
        job_tasks_getter: JobTasksGetter,
        workspace_builder_getter: Callable[[], Any],
        neo4j_graph_projector_getter: Callable[[], Any],
        graphrag_indexer_getter: Callable[[], Any],
        ingest_helpers_getter: Callable[[], Module4IngestRuntimeHelpers],
        query_helpers_getter: Callable[[], Module4QueryRuntimeHelpers],
        insight_helpers_getter: Callable[[], Module4InsightRuntimeHelpers],
        logger: Any,
        tenant_from_request_fn: Callable[[Optional[Request], Optional[str]], str] = tenant_from_request,
        parse_csv_list_fn: Callable[[Optional[str]], List[str]] = parse_csv_list,
        now_utc_fn: Callable[[], datetime] = now_utc,
        derived_ingest_batch_key_fn: Callable[[IngestRequest, Optional[str]], str] = derived_ingest_batch_key,
        cors_origins_factory: Callable[[], tuple[list[str], bool]] = cors_origins,
        build_lifespan_fn: Callable[..., Callable[[FastAPI], Any]] = build_lifespan,
        schedule_background_job_fn: Callable[..., None] = schedule_background_job,
        update_job_stage_fn: Callable[..., Awaitable[None]] = None,
        recover_jobs_fn: Callable[..., Awaitable[None]] = None,
        process_document_fn: Callable[..., Awaitable[Dict[str, int]]] = None,
        run_document_ingest_job_fn: Callable[..., Awaitable[Dict[str, Any]]] = None,
        run_ingest_job_fn: Callable[..., Awaitable[None]] = None,
        run_rebuild_job_fn: Callable[..., Awaitable[None]] = None,
        submit_ingest_job_fn: Callable[..., Awaitable[IngestResponse]] = None,
    ) -> None:
        self._storage_getter = storage_getter
        self._job_tasks_getter = job_tasks_getter
        self._workspace_builder_getter = workspace_builder_getter
        self._neo4j_graph_projector_getter = neo4j_graph_projector_getter
        self._graphrag_indexer_getter = graphrag_indexer_getter
        self._ingest_helpers_getter = ingest_helpers_getter
        self._query_helpers_getter = query_helpers_getter
        self._insight_helpers_getter = insight_helpers_getter
        self._logger = logger
        self._tenant_from_request = tenant_from_request_fn
        self._parse_csv_list = parse_csv_list_fn
        self._now_utc = now_utc_fn
        self._derived_ingest_batch_key = derived_ingest_batch_key_fn
        self._cors_origins_factory = cors_origins_factory
        self._build_lifespan = build_lifespan_fn
        self._schedule_background_job = schedule_background_job_fn
        self._update_job_stage_fn = update_job_stage_fn or update_job_stage
        self._recover_jobs_fn = recover_jobs_fn or recover_jobs
        self._process_document_fn = process_document_fn or process_document
        self._run_document_ingest_job_fn = run_document_ingest_job_fn or run_document_ingest_job
        self._run_ingest_job_fn = run_ingest_job_fn or run_ingest_job
        self._run_rebuild_job_fn = run_rebuild_job_fn or run_rebuild_job
        self._submit_ingest_job_fn = submit_ingest_job_fn or submit_ingest_job

    @property
    def storage_getter(self) -> StorageGetter:
        return self._storage_getter

    @property
    def job_tasks_getter(self) -> JobTasksGetter:
        return self._job_tasks_getter

    @property
    def workspace_builder_getter(self) -> Callable[[], Any]:
        return self._workspace_builder_getter

    @property
    def neo4j_graph_projector_getter(self) -> Callable[[], Any]:
        return self._neo4j_graph_projector_getter

    @property
    def graphrag_indexer_getter(self) -> Callable[[], Any]:
        return self._graphrag_indexer_getter

    @property
    def tenant_from_request(self) -> Callable[[Optional[Request], Optional[str]], str]:
        return self._tenant_from_request

    @property
    def parse_csv_list(self) -> Callable[[Optional[str]], List[str]]:
        return self._parse_csv_list

    @property
    def now_utc(self) -> Callable[[], datetime]:
        return self._now_utc

    @property
    def query_helpers(self) -> Module4QueryRuntimeHelpers:
        return self._query_helpers_getter()

    @property
    def insight_helpers(self) -> Module4InsightRuntimeHelpers:
        return self._insight_helpers_getter()

    def cors_origins(self) -> tuple[list[str], bool]:
        return self._cors_origins_factory()

    def build_router_deps_kwargs(
        self,
        *,
        submit_ingest_job: Callable[[IngestRequest, Request], Awaitable[IngestResponse]],
        schedule_rebuild_job: ScheduleRebuildJobCallback,
    ) -> Dict[str, Any]:
        return {
            "storage_getter": self.storage_getter,
            "query_helpers": self.query_helpers,
            "insight_helpers": self.insight_helpers,
            "workspace_builder_getter": self.workspace_builder_getter,
            "neo4j_graph_projector_getter": self.neo4j_graph_projector_getter,
            "graphrag_indexer_getter": self.graphrag_indexer_getter,
            "tenant_from_request": self.tenant_from_request,
            "parse_csv_list": self.parse_csv_list,
            "submit_ingest_job": submit_ingest_job,
            "schedule_rebuild_job": schedule_rebuild_job,
            "now_utc": self.now_utc,
        }

    def build_lifespan(
        self,
        *,
        recover_jobs_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> Callable[[FastAPI], Any]:
        return self._build_lifespan(
            storage_getter=self._storage_getter,
            job_tasks_getter=self._job_tasks_getter,
            recover_jobs_callback=recover_jobs_callback or self.recover_jobs,
            logger=self._logger,
        )

    async def update_job_stage(
        self,
        job_id: str,
        *,
        stage: str,
        progress: float,
        base_result: Optional[Dict[str, Any]] = None,
        **updates: Any,
    ) -> None:
        await self._update_job_stage_fn(
            storage=self._storage_getter(),
            job_id=job_id,
            stage=stage,
            progress=progress,
            base_result=base_result,
            **updates,
        )

    async def recover_jobs(self) -> None:
        await self._recover_jobs_fn(
            storage=self._storage_getter(),
            helpers=self._ingest_helpers_getter(),
            job_tasks=self._job_tasks_getter(),
            schedule_ingest_job=self.schedule_ingest_job,
            schedule_rebuild_job=self.schedule_rebuild_job,
        )

    async def process_document(
        self,
        *,
        tenant_id: str,
        batch_id: str,
        graph_file_id: Optional[str],
        doc: Dict[str, Any],
    ) -> Dict[str, int]:
        return await self._process_document_fn(
            storage=self._storage_getter(),
            helpers=self._ingest_helpers_getter(),
            tenant_id=tenant_id,
            batch_id=batch_id,
            graph_file_id=graph_file_id,
            doc=doc,
        )

    def schedule_ingest_job(self, job_id: str, batch_id: str, payload: IngestRequest) -> None:
        self._schedule_background_job(
            job_tasks_getter=self._job_tasks_getter,
            job_id=job_id,
            coroutine_factory=lambda: self.run_ingest_job(job_id, batch_id, payload),
        )

    def schedule_rebuild_job(self, job_id: str, payload: RebuildRequest) -> None:
        self._schedule_background_job(
            job_tasks_getter=self._job_tasks_getter,
            job_id=job_id,
            coroutine_factory=lambda: self.run_rebuild_job(job_id, payload),
        )

    async def run_document_ingest_job(
        self,
        job_id: str,
        batch_id: str,
        payload: IngestRequest,
        *,
        process_document_callback: Callable[..., Awaitable[Dict[str, int]]] | None = None,
        update_job_stage_callback: Callable[..., Awaitable[None]] | None = None,
    ) -> Dict[str, Any]:
        return await self._run_document_ingest_job_fn(
            storage=self._storage_getter(),
            helpers=self._ingest_helpers_getter(),
            job_id=job_id,
            batch_id=batch_id,
            payload=payload,
            process_document_callback=process_document_callback or self.process_document,
            update_job_stage_callback=update_job_stage_callback or self.update_job_stage,
        )

    async def run_ingest_job(
        self,
        job_id: str,
        batch_id: str,
        payload: IngestRequest,
        *,
        run_document_ingest_job_callback: RunDocumentIngestJobCallback | None = None,
    ) -> None:
        await self._run_ingest_job_fn(
            storage=self._storage_getter(),
            job_tasks=self._job_tasks_getter(),
            helpers=self._ingest_helpers_getter(),
            job_id=job_id,
            batch_id=batch_id,
            payload=payload,
            run_document_ingest_job_callback=run_document_ingest_job_callback or self.run_document_ingest_job,
        )

    async def run_rebuild_job(
        self,
        job_id: str,
        payload: RebuildRequest,
        *,
        run_document_ingest_job_callback: RunDocumentIngestJobCallback | None = None,
    ) -> None:
        await self._run_rebuild_job_fn(
            storage=self._storage_getter(),
            job_tasks=self._job_tasks_getter(),
            helpers=self._ingest_helpers_getter(),
            job_id=job_id,
            payload=payload,
            run_document_ingest_job_callback=run_document_ingest_job_callback or self.run_document_ingest_job,
        )

    async def submit_ingest_job(
        self,
        payload: IngestRequest,
        request: Request,
        *,
        schedule_ingest_job_callback: ScheduleIngestJobCallback | None = None,
    ) -> IngestResponse:
        tenant_id = self._tenant_from_request(request, payload.tenant_id)
        try:
            return await self._submit_ingest_job_fn(
                storage=self._storage_getter(),
                payload=payload,
                tenant_id=tenant_id,
                derived_ingest_batch_key=self._derived_ingest_batch_key,
                schedule_ingest_job=schedule_ingest_job_callback or self.schedule_ingest_job,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
