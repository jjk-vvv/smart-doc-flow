from __future__ import annotations

"""Compatibility alias for legacy frontend-static service import path."""

import sys

from app.services import frontend_static_service as _canonical_module

sys.modules[__name__] = _canonical_module
