from __future__ import annotations

"""Backward-compatible root router shim.

Canonical compatibility router now lives under ``app.api.compat.router``.
"""

from .api.compat.router import (
    Module4RouterDeps,
    build_module4_router,
    graphrag_query_response_service,
)

__all__ = [
    "Module4RouterDeps",
    "build_module4_router",
    "graphrag_query_response_service",
]
