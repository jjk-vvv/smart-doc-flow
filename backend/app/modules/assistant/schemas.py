from __future__ import annotations

"""Compatibility alias for legacy assistant schema import path."""

import sys

from app.domain import assistant as _canonical_module

sys.modules[__name__] = _canonical_module
