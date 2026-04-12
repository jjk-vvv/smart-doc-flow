from __future__ import annotations

"""Backward-compatible module4-sync router shim.

Canonical compatibility module now lives under ``app.api.compat``.
"""

try:
    from ..api.compat.module4_sync_router import build_module4_sync_router
except (ImportError, ModuleNotFoundError):  # pragma: no cover - direct file-loading tests can fall back to plain imports
    from module2.app.api.compat.module4_sync_router import build_module4_sync_router


__all__ = [
    "build_module4_sync_router",
]
