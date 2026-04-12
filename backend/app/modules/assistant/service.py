"""Compatibility alias for legacy assistant service import path.

This module intentionally aliases to ``app.services.assistant_service`` so that:
1) legacy imports keep working, and
2) monkey patching the legacy path mutates the canonical module namespace.
"""

from __future__ import annotations

import sys

from app.services import assistant_service as _canonical_module

sys.modules[__name__] = _canonical_module
