from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .extraction import TraceHit


class SummarizeRequest(BaseModel):
    file_name: str = Field(..., min_length=1)
    result: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    soft_warnings: List[str] = Field(default_factory=list)
    trace_hits: List[TraceHit] = Field(default_factory=list)
    max_chars: int = Field(default=400, ge=120, le=4000)


class SummarizeResponse(BaseModel):
    summary: str

