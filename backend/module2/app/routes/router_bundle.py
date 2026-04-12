from __future__ import annotations

"""Backward-compatible router shim.

Canonical compatibility router now lives under ``app.api.compat.router_bundle``.
"""

from ..api.compat.router_bundle import build_module2_routers

__all__ = [
    "build_module2_routers",
]
