from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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

