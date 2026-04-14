from __future__ import annotations

"""Compatibility adapter for extraction builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import extraction_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import extraction_builder as _service_module  # type: ignore[import-not-found]


_EXTRACTION_RUNTIME_FINGERPRINT_FILES = _service_module._EXTRACTION_RUNTIME_FINGERPRINT_FILES
BoundedEnvIntFn = _service_module.BoundedEnvIntFn
GetEnvFn = _service_module.GetEnvFn
Module2MainExtractionBundle = _service_module.Module2MainExtractionBundle
build_module2_main_extraction_bundle = _service_module.build_module2_main_extraction_bundle


__all__ = [
    "_EXTRACTION_RUNTIME_FINGERPRINT_FILES",
    "BoundedEnvIntFn",
    "GetEnvFn",
    "Module2MainExtractionBundle",
    "build_module2_main_extraction_bundle",
]


