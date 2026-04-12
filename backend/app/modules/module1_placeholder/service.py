from __future__ import annotations

"""Compatibility alias for legacy module1-placeholder service import path."""

import sys

from app.services import module1_placeholder_service as _canonical_module

sys.modules[__name__] = _canonical_module
