from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal["module2", "module3", "manual", "api"]
JobType = Literal["ingest", "rebuild_graph", "run_rules", "simulate"]
JobStatus = Literal["queued", "running", "success", "failed", "cancelled"]
AlertSeverity = Literal["yellow", "orange", "red"]
AlertStatus = Literal["open", "ack", "resolved", "false_positive"]
RuleKind = Literal["deterministic", "semantic", "anomaly"]


class IngestRequest(BaseModel):
    tenant_id: str = "default"
    source: SourceType = "module2"
    source_batch_key: Optional[str] = None
    documents: List[Dict[str, Any]] = Field(default_factory=list, min_length=1)


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


class ExplainRequest(BaseModel):
    alert_id: Optional[str] = None
    node_id: Optional[str] = None
    target_node_id: Optional[str] = None


class ExplainResponse(BaseModel):
    conclusion: str
    reasoning_steps: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class SimulateRequest(BaseModel):
    tenant_id: str = "default"
    scenario_name: str = "default-scenario"
    params: Dict[str, Any] = Field(default_factory=dict)
    scope: Dict[str, Any] = Field(default_factory=dict)


class SimulateResponse(BaseModel):
    impacts: List[Dict[str, Any]] = Field(default_factory=list)
    changed_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class HealthzResponse(BaseModel):
    status: str
    db_connected: bool
    degraded_memory_mode: bool
    jobs_in_queue: int
    now: datetime
