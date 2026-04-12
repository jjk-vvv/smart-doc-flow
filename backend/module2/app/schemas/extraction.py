from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class ExtractionRequest(BaseModel):
    """API-level request model (binary payload mode)."""

    model_config = ConfigDict(populate_by_name=True)

    files: List[bytes] = Field(..., min_length=1, max_length=5)
    schema_payload: Dict[str, Any] = Field(default_factory=dict, alias="schema")


class ExtractedEntity(BaseModel):
    """Single extracted field with visual grounding."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_ref_id: Optional[str] = None
    bbox: List[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_bbox_shape(self) -> "ExtractedEntity":
        if self.source_ref_id and self.bbox and len(self.bbox) != 5:
            raise ValueError("bbox must be [page, x, y, w, h] when provided")
        return self


class ExtractionResult(RootModel[Dict[str, ExtractedEntity]]):
    """Field name -> extracted entity."""


class TraceHit(BaseModel):
    """Normalized trace hit for field/table/figure localization."""

    file_name: str = ""
    file_hash: str = ""
    object_type: str = "field"
    object_id: str = ""
    ref_id: Optional[str] = None
    page: Optional[int] = None
    snippet: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    locator: Dict[str, Any] = Field(default_factory=dict)
    bbox: List[float] = Field(default_factory=list)
    artifact_path: Optional[str] = None
    artifact_url: Optional[str] = None
    match_reason: str = ""


class DocumentExtractionResponse(BaseModel):
    file_name: str
    file_hash: str
    track: str
    cached: bool
    result: ExtractionResult
    errors: List[str] = Field(default_factory=list)
    soft_warnings: List[str] = Field(default_factory=list)
    trace_hits: List[TraceHit] = Field(default_factory=list)
    trace_stats: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class BatchExtractionResponse(BaseModel):
    documents: List[DocumentExtractionResponse]

