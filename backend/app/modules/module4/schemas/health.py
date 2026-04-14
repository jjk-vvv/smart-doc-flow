from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .graph import GraphProjectionRuntimeStatus


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
    runtime_profile: Dict[str, Any] = Field(default_factory=dict)
    env_mapping: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    tiktoken_encoding_ready: Optional[bool] = None
    tiktoken_encoding_error_message: Optional[str] = None
    provider_api: RuntimeDependencyStatus = Field(default_factory=RuntimeDependencyStatus)
    neo4j: RuntimeDependencyStatus = Field(default_factory=RuntimeDependencyStatus)


class HealthzResponse(BaseModel):
    status: str
    db_connected: bool
    jobs_in_queue: int
    last_connect_error: Optional[str] = None
    graphrag: GraphRAGRuntimeStatus = Field(default_factory=GraphRAGRuntimeStatus)
    projection_runtime: GraphProjectionRuntimeStatus = Field(default_factory=GraphProjectionRuntimeStatus)
    now: datetime

