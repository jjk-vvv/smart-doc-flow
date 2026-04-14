from __future__ import annotations

"""Compatibility shim for module2 main quality bundle builders.

The canonical implementation has moved to
``module2.app.services.extraction.quality_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.extraction import quality_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.extraction import quality_builder as _bootstrap_module  # type: ignore[import-not-found]


BoolFactory = _bootstrap_module.BoolFactory
Module2MainQualityBundle = _bootstrap_module.Module2MainQualityBundle
build_module2_main_quality_bundle = _bootstrap_module.build_module2_main_quality_bundle


__all__ = [
    "BoolFactory",
    "Module2MainQualityBundle",
    "build_module2_main_quality_bundle",
]

