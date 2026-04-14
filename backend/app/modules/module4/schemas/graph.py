from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .evidence import EvidenceItem


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
    evidence: List[EvidenceItem] = Field(default_factory=list)
    edge_evidence: Dict[str, List[EvidenceItem]] = Field(default_factory=dict)

