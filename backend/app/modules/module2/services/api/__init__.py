"""Module2 API-facing services.

This package hosts the canonical service entrypoints consumed by module2 API
routers. Legacy imports from ``app.services.*`` remain available through thin
compatibility wrappers.
"""

from .assistant_service import AssistantService, get_assistant_service
from .extraction_service import ExtractionService, get_extraction_service

__all__ = [
    "AssistantService",
    "ExtractionService",
    "get_assistant_service",
    "get_extraction_service",
]
