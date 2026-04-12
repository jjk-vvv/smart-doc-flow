from __future__ import annotations

"""Compatibility alias for legacy assistant config import path."""

import sys

from app.core import assistant_config as _canonical_module

sys.modules[__name__] = _canonical_module
