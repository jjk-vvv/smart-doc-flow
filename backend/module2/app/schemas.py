from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class ExtractionRequest(BaseModel):
    """API-level request model (binary payload mode)."""

    files: List[bytes] = Field(..., min_length=1, max_length=5)
    schema: Dict[str, Any] = Field(default_factory=dict)


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


class DocumentExtractionResponse(BaseModel):
    file_name: str
    file_hash: str
    track: str
    cached: bool
    result: ExtractionResult
    errors: List[str] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class BatchExtractionResponse(BaseModel):
    documents: List[DocumentExtractionResponse]
