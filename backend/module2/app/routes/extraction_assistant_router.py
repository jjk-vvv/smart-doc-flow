from __future__ import annotations

"""Backward-compatible extraction-assistant router shim.

Canonical compatibility module now lives under ``app.api.compat``.
"""

try:
    from ..api.compat.extraction_assistant_router import build_extraction_assistant_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.compat.extraction_assistant_router import build_extraction_assistant_router

__all__ = [
    "build_extraction_assistant_router",
]
