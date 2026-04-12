from __future__ import annotations

"""Compatibility shim for module2 main geometry bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.geometry_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import geometry_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import geometry_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainGeometryBundle = _bootstrap_module.Module2MainGeometryBundle
build_module2_main_geometry_bundle = _bootstrap_module.build_module2_main_geometry_bundle


__all__ = [
    "Module2MainGeometryBundle",
    "build_module2_main_geometry_bundle",
]
