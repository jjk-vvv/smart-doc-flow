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


class BridgeFilePayload(BaseModel):
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    file_base64: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    base64: Optional[str] = None

    @model_validator(mode="after")
    def _validate_source(self) -> "BridgeFilePayload":
        url_value = (self.file_url or self.url or "").strip()
        base64_value = (self.file_base64 or self.base64 or "").strip()
        if bool(url_value) == bool(base64_value):
            raise ValueError("Provide exactly one source: file_url|url or file_base64|base64.")
        return self

    def pick_name(self, idx: int) -> str:
        raw = (self.file_name or self.name or "").strip()
        if raw:
            return raw
        if (self.file_url or self.url or "").strip():
            return f"remote_{idx}"
        return f"inline_{idx}"

    def pick_url(self) -> str:
        return (self.file_url or self.url or "").strip()

    def pick_base64(self) -> str:
        return (self.file_base64 or self.base64 or "").strip()


class BridgeJobCreateRequest(BaseModel):
    request_id: Optional[str] = None
    schema: Dict[str, Any] = Field(default_factory=dict)
    files: List[BridgeFilePayload] = Field(..., min_length=1, max_length=5)
    max_retries: int = Field(default=2, ge=0, le=6)


class BridgeJobStatusRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=128)
    include_documents: bool = False


class BridgeTraceLocateRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=128)
    field_name: Optional[str] = None
    file_name: Optional[str] = None
    file_hash: Optional[str] = None
    ref_id: Optional[str] = None
    object_type: Optional[str] = None
    keyword: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)


class SummarizeRequest(BaseModel):
    file_name: str = Field(..., min_length=1)
    result: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    soft_warnings: List[str] = Field(default_factory=list)
    max_chars: int = Field(default=400, ge=120, le=4000)


class SummarizeResponse(BaseModel):
    summary: str


class AssistantQueryRequest(BaseModel):
    document: DocumentExtractionResponse
    summary: str = ""
    user_instruction: str = Field(..., min_length=1, max_length=2000)
    persist: bool = False
    top_k: int = Field(default=12, ge=1, le=80)


class AssistantQueryResponse(BaseModel):
    ok: bool = True
    answer: str
    summary_used: str = ""
    matched_fields: List[Dict[str, Any]] = Field(default_factory=list)
    matched_trace_hits: List[TraceHit] = Field(default_factory=list)
    persisted: bool = False
    persisted_rows: int = 0
    warnings: List[str] = Field(default_factory=list)


class CacheClearResponse(BaseModel):
    ok: bool = True
    message: str
    cache_counts: Dict[str, int] = Field(default_factory=dict)
    removed_artifacts: int = 0
