"""Compatibility schema export surface for module2.

Canonical definitions now live in focused schema modules:
- extraction
- trace
- summarize
- cache
"""

from .cache import CacheClearResponse
from .extraction import (
    BatchExtractionResponse,
    DocumentExtractionResponse,
    ExtractedEntity,
    ExtractionRequest,
    ExtractionResult,
    TraceHit,
)
from .summarize import SummarizeRequest, SummarizeResponse
from .trace import TraceLocateRequest, TraceLocateResponse

__all__ = [
    "ExtractionRequest",
    "ExtractedEntity",
    "ExtractionResult",
    "TraceHit",
    "DocumentExtractionResponse",
    "BatchExtractionResponse",
    "TraceLocateRequest",
    "TraceLocateResponse",
    "SummarizeRequest",
    "SummarizeResponse",
    "CacheClearResponse",
]
