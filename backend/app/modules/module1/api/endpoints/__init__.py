"""Module1 API endpoint implementations."""

from .document import router as document_router
from .health import router as health_router
from .module1_placeholder import router as module1_placeholder_router

__all__ = ["document_router", "health_router", "module1_placeholder_router"]
