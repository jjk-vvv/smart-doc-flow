from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .extraction import DocumentExtractionResponse, TraceHit


class TraceLocateRequest(BaseModel):
    document: DocumentExtractionResponse
    field_name: Optional[str] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    ref_id: Optional[str] = None
    object_type: Optional[str] = None
    keyword: Optional[str] = None
    top_k: int = Field(default=8, ge=1, le=120)


class TraceLocateResponse(BaseModel):
    hit_count: int = 0
    truncated: bool = False
    hits: List[TraceHit] = Field(default_factory=list)

