from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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

