from __future__ import annotations

"""Backward-compatible module path for document tools runtime."""

try:  # pragma: no cover - exercised across different loader contexts
    from .document.tools import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - direct file loading fallback for tests
    from app.modules.module2.services.document.tools import *  # noqa: F401,F403
