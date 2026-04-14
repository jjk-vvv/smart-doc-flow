from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .common import AlertSeverity, AlertStatus


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

