from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


SourceType = Literal["module2"]
JobType = Literal["ingest", "rebuild_graph", "run_rules", "simulate"]
JobStatus = Literal["queued", "running", "success", "failed", "cancelled"]
AlertSeverity = Literal["yellow", "orange", "red"]
AlertStatus = Literal["open", "ack", "resolved", "false_positive"]
RuleKind = Literal["deterministic"]


class IngestRequest(BaseModel):
    tenant_id: str = ""
    source: SourceType = "module2"
    source_batch_key: Optional[str] = None
    graph_mode: str = "hybrid"
    documents: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_has_input(self) -> "IngestRequest":
        if self.documents:
            return self
        raise ValueError("At least one document is required")


class IngestResponse(BaseModel):
    job_id: str
    batch_id: str
    status: JobStatus


class JobResponse(BaseModel):
    job_id: str
    tenant_id: str
    job_type: JobType
    status: JobStatus
    progress: float = 0.0
    error_message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class GraphNode(BaseModel):
    node_id: str
    node_type: str
    canonical_key: str
    display_name: str
    confidence: float = 0.0
    attrs: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class GraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    direction: str = "out"
    confidence: float = 0.0
    risk_score: float = 0.0
    attrs: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class GraphStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    by_node_type: Dict[str, int] = Field(default_factory=dict)
    by_relation_type: Dict[str, int] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    stats: GraphStats = Field(default_factory=GraphStats)
    source: Optional[str] = None
    workspace_id: Optional[str] = None


class GraphProjectionStatus(BaseModel):
    status: str = ""
    projected_nodes: int = 0
    projected_edges: int = 0
    source_node_count: int = 0
    source_edge_count: int = 0
    skipped_reason: Optional[str] = None
    error_message: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    relationship_type: str = "MODULE4_EDGE"


class GraphProjectionRuntimeStatus(BaseModel):
    enabled: bool = False
    configured: bool = False
    can_project: bool = False
    database: str = "neo4j"
    max_nodes: int = 0
    max_edges: int = 0
    timeout_sec: float = 0.0
    missing_fields: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    relationship_type: str = "MODULE4_EDGE"


class GraphFileItem(BaseModel):
    graph_file_id: str
    tenant_id: str
    file_hash: str
    file_name: str
    workspace_id: Optional[str] = None
    graph_mode: str = "hybrid"
    source: str = "module2"
    status: str = "queued"
    current_job_id: Optional[str] = None
    active_version_id: Optional[str] = None
    last_error: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    projection: Optional[GraphProjectionStatus] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None


class GraphFileListResponse(BaseModel):
    items: List[GraphFileItem] = Field(default_factory=list)


class GraphFileDetailResponse(BaseModel):
    item: GraphFileItem


class GraphNodeDetailResponse(BaseModel):
    node: Optional[GraphNode] = None
    graph: GraphResponse = Field(default_factory=GraphResponse)
    file: Optional[GraphFileItem] = None
    evidence: List["EvidenceItem"] = Field(default_factory=list)
    edge_evidence: Dict[str, List["EvidenceItem"]] = Field(default_factory=dict)


class AlertItem(BaseModel):
    alert_id: str
    rule_id: str
    severity: AlertSeverity
    status: AlertStatus
    subject_node_id: Optional[str] = None
    title: str
    summary: str
    risk_score: float = 0.0
    payload: Dict[str, Any] = Field(default_factory=dict)
    detected_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlertListResponse(BaseModel):
    total: int
    items: List[AlertItem] = Field(default_factory=list)


class AlertActionRequest(BaseModel):
    tenant_id: Optional[str] = None
    actor: str = "user"
    comment: str = ""


class AlertResolveRequest(AlertActionRequest):
    resolution: str = ""


class AlertActionResponse(BaseModel):
    ok: bool
    alert: Optional[AlertItem] = None


class EvidenceItem(BaseModel):
    evidence_id: str
    doc_id: str
    object_type: str
    object_id: str = ""
    ref_id: Optional[str] = None
    page_no: Optional[int] = None
    snippet: str = ""
    locator: Dict[str, Any] = Field(default_factory=dict)
    bbox: List[Any] = Field(default_factory=list)
    artifact_url: Optional[str] = None
    confidence: float = 0.0
    created_at: Optional[datetime] = None


class EvidenceListResponse(BaseModel):
    total: int
    items: List[EvidenceItem] = Field(default_factory=list)


class RuleItem(BaseModel):
    rule_id: str
    name: str
    severity: AlertSeverity
    rule_kind: RuleKind
    expr: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    version: int = 1
    updated_at: Optional[datetime] = None


class RuleListResponse(BaseModel):
    items: List[RuleItem] = Field(default_factory=list)


class RuleUpsertRequest(BaseModel):
    name: str
    severity: AlertSeverity
    rule_kind: RuleKind
    expr: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RuleUpsertResponse(BaseModel):
    ok: bool
    rule: RuleItem


class RebuildRequest(BaseModel):
    tenant_id: str = ""


class RebuildResponse(BaseModel):
    job_id: str
    status: JobStatus
    batches: int = 0
    documents: int = 0


class ExplainRequest(BaseModel):
    tenant_id: Optional[str] = None
    alert_id: Optional[str] = None
    node_id: Optional[str] = None
    target_node_id: Optional[str] = None


class ExplainResponse(BaseModel):
    conclusion: str
    reasoning_steps: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class SimulateRequest(BaseModel):
    tenant_id: str = ""
    scenario_name: str = "default-scenario"
    params: Dict[str, Any] = Field(default_factory=dict)
    scope: Dict[str, Any] = Field(default_factory=dict)


class SimulateResponse(BaseModel):
    impacts: List[Dict[str, Any]] = Field(default_factory=list)
    changed_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class RuntimeDependencyStatus(BaseModel):
    configured: bool = False
    reachable: Optional[bool] = None
    missing_fields: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class GraphRAGRuntimeStatus(BaseModel):
    ready: bool = False
    check_mode: str = "basic"
    python_bin: str = ""
    python_bin_exists: bool = False
    graphrag_module_available: bool = False
    module_error_message: Optional[str] = None
    prompt_assets_root: str = ""
    prompt_assets_ok: bool = False
    missing_prompt_assets: List[str] = Field(default_factory=list)
    config_missing_fields: List[str] = Field(default_factory=list)
    runtime_versions: Dict[str, str] = Field(default_factory=dict)
    tiktoken_encoding_ready: Optional[bool] = None
    tiktoken_encoding_error_message: Optional[str] = None
    oneapi: RuntimeDependencyStatus = Field(default_factory=RuntimeDependencyStatus)
    neo4j: RuntimeDependencyStatus = Field(default_factory=RuntimeDependencyStatus)


class HealthzResponse(BaseModel):
    status: str
    db_connected: bool
    jobs_in_queue: int
    last_connect_error: Optional[str] = None
    graphrag: GraphRAGRuntimeStatus = Field(default_factory=GraphRAGRuntimeStatus)
    projection_runtime: GraphProjectionRuntimeStatus = Field(default_factory=GraphProjectionRuntimeStatus)
    now: datetime
