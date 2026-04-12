from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .common import JobStatus, JobType, SourceType


class IngestRequest(BaseModel):
    tenant_id: str = ""
    source: SourceType = "module2"
    source_batch_key: Optional[str] = None
    graph_mode: str = "hybrid"
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    text_corpus: str = ""
    source_texts: List[Dict[str, Any]] = Field(default_factory=list)
    settings_overrides: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_has_input(self) -> "IngestRequest":
        if self.documents:
            return self
        if str(self.text_corpus or "").strip():
            return self
        if self.source_texts:
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


class RebuildRequest(BaseModel):
    tenant_id: str = ""


class RebuildResponse(BaseModel):
    job_id: str
    status: JobStatus
    batches: int = 0
    documents: int = 0

