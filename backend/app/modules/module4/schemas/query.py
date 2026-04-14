from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .common import GraphRAGQueryMode


class GraphRAGQueryRequest(BaseModel):
    tenant_id: str = ""
    file_hash: str
    query: str
    mode: GraphRAGQueryMode = "local"
    response_type: str = "multiple paragraphs"
    community_level: Optional[int] = 2
    dynamic_community_selection: bool = False
    verbose: bool = False

    @model_validator(mode="after")
    def validate_required_fields(self) -> "GraphRAGQueryRequest":
        if not str(self.file_hash or "").strip():
            raise ValueError("file_hash is required")
        if not str(self.query or "").strip():
            raise ValueError("query is required")
        return self


class GraphRAGQueryResponse(BaseModel):
    answer: str
    mode: GraphRAGQueryMode
    query: str
    response_type: str
    community_level: Optional[int] = None
    dynamic_community_selection: bool = False
    file_hash: str
    graph_file_id: Optional[str] = None
    active_version_id: Optional[str] = None
    workspace_id: Optional[str] = None
    context_data: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    linked_node_ids: List[str] = Field(default_factory=list)
    linked_node_resolution: Dict[str, Any] = Field(default_factory=dict)
    source: str = "graphrag:query"
