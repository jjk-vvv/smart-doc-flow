from __future__ import annotations

"""Compatibility alias for legacy extraction schema import path."""

import sys

from app.domain import extraction as _canonical_module

sys.modules[__name__] = _canonical_module
