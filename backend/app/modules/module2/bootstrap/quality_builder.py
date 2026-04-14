from __future__ import annotations

"""Compatibility adapter for quality builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import quality_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import quality_builder as _service_module  # type: ignore[import-not-found]


BoolFactory = _service_module.BoolFactory
Module2MainQualityBundle = _service_module.Module2MainQualityBundle
build_module2_main_quality_bundle = _service_module.build_module2_main_quality_bundle


__all__ = [
    "BoolFactory",
    "Module2MainQualityBundle",
    "build_module2_main_quality_bundle",
]


