from __future__ import annotations

"""Backward-compatible extraction-request router shim.

Canonical compatibility module now lives under ``app.api.compat``.
"""

try:
    from ..api.compat.extraction_request_router import build_extraction_request_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.compat.extraction_request_router import build_extraction_request_router

__all__ = [
    "build_extraction_request_router",
]
