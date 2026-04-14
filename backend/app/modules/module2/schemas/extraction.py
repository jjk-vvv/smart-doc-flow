from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ExtractionRequest(ExtractionModel):
    files: list[bytes] = Field(..., min_length=1, max_length=5)
    schema_payload: dict[str, Any] = Field(default_factory=dict, alias="schema")


class ExtractedEntity(ExtractionModel):
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ref_id: str | None = None
    bbox: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bbox_shape(self) -> "ExtractedEntity":
        if self.source_ref_id and self.bbox and len(self.bbox) != 5:
            raise ValueError("bbox must be [page, x, y, w, h] when provided")
        return self


class ExtractionResult(RootModel[dict[str, ExtractedEntity]]):
    pass


class TraceHit(ExtractionModel):
    file_name: str = ""
    file_hash: str = ""
    object_type: str = "field"
    object_id: str = ""
    ref_id: str | None = None
    page: int | None = None
    snippet: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    locator: dict[str, Any] = Field(default_factory=dict)
    bbox: list[float] = Field(default_factory=list)
    artifact_path: str | None = None
    artifact_url: str | None = None
    artifact_file_id: str | None = None
    artifact_download_url: str | None = None
    artifact_by_file_url: str | None = None
    match_reason: str = ""


class DocumentExtractionResponse(ExtractionModel):
    file_name: str
    file_hash: str
    track: str = ""
    cached: bool = False
    result: ExtractionResult
    errors: list[str] = Field(default_factory=list)
    soft_warnings: list[str] = Field(default_factory=list)
    trace_hits: list[TraceHit] = Field(default_factory=list)
    trace_stats: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BatchExtractionResponse(ExtractionModel):
    documents: list[DocumentExtractionResponse] = Field(default_factory=list)


class CancelExtractionJobFileRequest(ExtractionModel):
    file_hash: str = ""
    file_name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> "CancelExtractionJobFileRequest":
        if not str(self.file_hash or "").strip() and not str(self.file_name or "").strip():
            raise ValueError("file_hash or file_name is required")
        return self


class CancelExtractionJobFileResponse(ExtractionModel):
    ok: bool = True
    job_id: str = ""
    file_hash: str = ""
    file_name: str = ""
    status: str = ""
    stage: str = ""
    already_terminal: bool = False


class TraceLocateRequest(ExtractionModel):
    document: DocumentExtractionResponse
    field_name: str | None = None
    file_name: str | None = None
    file_hash: str | None = None
    ref_id: str | None = None
    object_type: str | None = None
    keyword: str | None = None
    top_k: int = Field(default=8, ge=1, le=120)


class TraceLocateResponse(ExtractionModel):
    hit_count: int = 0
    truncated: bool = False
    hits: list[TraceHit] = Field(default_factory=list)


class SummarizeRequest(ExtractionModel):
    file_name: str = Field(..., min_length=1)
    result: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    soft_warnings: list[str] = Field(default_factory=list)
    trace_hits: list[TraceHit] = Field(default_factory=list)
    max_chars: int = Field(default=400, ge=120, le=4000)


class SummarizeResponse(ExtractionModel):
    summary: str


class CacheClearResponse(ExtractionModel):
    ok: bool = True
    message: str
    scope: str = "results"
    cache_counts: dict[str, int] = Field(default_factory=dict)
    removed_artifacts: int = 0
    removed_runtime_models: int = 0
    removed_materialized: dict[str, int] = Field(default_factory=dict)
    process_pool_reset_generation: int = 0


class Assistant1HistoryMessage(ExtractionModel):
    role: str = Field(default="user", pattern="^(system|user|assistant|developer)$")
    content: str = Field(default="", max_length=20000)


class Assistant1ClientCaps(ExtractionModel):
    supports_replace: bool = True


class Assistant1ChatStreamRequest(ExtractionModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=128)
    file_hash: str = Field(default="", max_length=128)
    history: list[Assistant1HistoryMessage] = Field(default_factory=list, max_length=24)
    top_k: int = Field(default=5, ge=1, le=8)
    max_steps: int = Field(default=6, ge=1, le=10)
    debug: bool = False
    resume_run_id: str = Field(default="", max_length=128)
    after_seq: int = Field(default=0, ge=0)
    client_caps: Assistant1ClientCaps = Field(default_factory=Assistant1ClientCaps)
    extra_context: dict[str, Any] = Field(default_factory=dict)
