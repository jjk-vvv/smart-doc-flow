from __future__ import annotations

"""Canonical endpoint surface for graph/ingest/query routes."""

try:
    from .module4 import build_router, graphrag_query_response_service
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from app.modules.module4.api.v1.endpoints.module4 import (
        build_router,
        graphrag_query_response_service,
    )

__all__ = [
    "build_router",
    "graphrag_query_response_service",
]
