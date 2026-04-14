from __future__ import annotations

"""Compatibility adapter for geometry builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import geometry_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import geometry_builder as _service_module  # type: ignore[import-not-found]


Module2MainGeometryBundle = _service_module.Module2MainGeometryBundle
build_module2_main_geometry_bundle = _service_module.build_module2_main_geometry_bundle


__all__ = [
    "Module2MainGeometryBundle",
    "build_module2_main_geometry_bundle",
]


