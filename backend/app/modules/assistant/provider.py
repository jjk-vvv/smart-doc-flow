from __future__ import annotations

"""Compatibility alias for legacy assistant provider import path."""

import sys

from app.integrations import assistant_provider as _canonical_module

sys.modules[__name__] = _canonical_module
