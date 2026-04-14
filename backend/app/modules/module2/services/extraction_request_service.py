from __future__ import annotations

"""Backward-compatible module path for extraction request runtime."""

try:  # pragma: no cover - exercised across different loader contexts
    from .extraction.request import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - direct file loading fallback for tests
    from app.modules.module2.services.extraction.request import *  # noqa: F401,F403
