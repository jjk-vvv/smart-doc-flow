from __future__ import annotations

"""Backward-compatible module path for module2 cache-clear composition runtime."""

try:  # pragma: no cover - exercised across different loader contexts
    from ..composition.cache_clear import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - direct file loading fallback for tests
    from app.modules.module2.composition.cache_clear import *  # noqa: F401,F403

