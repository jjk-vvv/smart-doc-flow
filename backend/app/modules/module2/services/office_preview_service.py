from __future__ import annotations

"""Backward-compatible module path for office preview runtime."""

try:  # pragma: no cover - exercised across different loader contexts
    from .preview.office import *  # noqa: F401,F403
except ImportError:  # pragma: no cover - direct file loading fallback for tests
    from app.modules.module2.services.preview.office import *  # noqa: F401,F403
