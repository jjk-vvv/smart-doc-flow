from __future__ import annotations

"""Compatibility alias for legacy extraction service import path."""

import sys

from app.services import extraction_service as _canonical_module

sys.modules[__name__] = _canonical_module
