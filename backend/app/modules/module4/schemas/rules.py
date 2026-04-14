from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .common import AlertSeverity, RuleKind


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

