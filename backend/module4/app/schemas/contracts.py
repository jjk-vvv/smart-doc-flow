"""Compatibility schema export surface for module4.

Canonical definitions now live in focused schema modules:
- common
- ingest
- graph
- query
- alerts
- evidence
- rules
- insights
- health
"""

from .alerts import (
    AlertActionRequest,
    AlertActionResponse,
    AlertItem,
    AlertListResponse,
    AlertResolveRequest,
)
from .common import (
    AlertSeverity,
    AlertStatus,
    GraphRAGQueryMode,
    JobStatus,
    JobType,
    RuleKind,
    SourceType,
)
from .evidence import EvidenceItem, EvidenceListResponse
from .graph import (
    GraphEdge,
    GraphFileDetailResponse,
    GraphFileItem,
    GraphFileListResponse,
    GraphNode,
    GraphNodeDetailResponse,
    GraphProjectionRuntimeStatus,
    GraphProjectionStatus,
    GraphResponse,
    GraphStats,
)
from .health import GraphRAGRuntimeStatus, HealthzResponse, RuntimeDependencyStatus
from .ingest import IngestRequest, IngestResponse, JobResponse, RebuildRequest, RebuildResponse
from .insights import ExplainRequest, ExplainResponse, SimulateRequest, SimulateResponse
from .query import GraphRAGQueryRequest, GraphRAGQueryResponse
from .rules import RuleItem, RuleListResponse, RuleUpsertRequest, RuleUpsertResponse

__all__ = [
    "SourceType",
    "JobType",
    "JobStatus",
    "AlertSeverity",
    "AlertStatus",
    "RuleKind",
    "IngestRequest",
    "IngestResponse",
    "JobResponse",
    "GraphNode",
    "GraphEdge",
    "GraphStats",
    "GraphResponse",
    "GraphProjectionStatus",
    "GraphProjectionRuntimeStatus",
    "GraphFileItem",
    "GraphFileListResponse",
    "GraphFileDetailResponse",
    "GraphNodeDetailResponse",
    "GraphRAGQueryMode",
    "GraphRAGQueryRequest",
    "GraphRAGQueryResponse",
    "AlertItem",
    "AlertListResponse",
    "AlertActionRequest",
    "AlertResolveRequest",
    "AlertActionResponse",
    "EvidenceItem",
    "EvidenceListResponse",
    "RuleItem",
    "RuleListResponse",
    "RuleUpsertRequest",
    "RuleUpsertResponse",
    "RebuildRequest",
    "RebuildResponse",
    "ExplainRequest",
    "ExplainResponse",
    "SimulateRequest",
    "SimulateResponse",
    "RuntimeDependencyStatus",
    "GraphRAGRuntimeStatus",
    "HealthzResponse",
]
