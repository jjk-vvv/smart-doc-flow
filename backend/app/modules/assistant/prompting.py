from __future__ import annotations

"""Compatibility alias for legacy assistant prompting import path."""

import sys

from app.services import assistant_prompting as _canonical_module

sys.modules[__name__] = _canonical_module
