from __future__ import annotations

"""Compatibility shim for module2 main extraction bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.extraction_builder`` and is exposed through
the bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import extraction_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import extraction_builder as _bootstrap_module  # type: ignore[import-not-found]


_EXTRACTION_RUNTIME_FINGERPRINT_FILES = _bootstrap_module._EXTRACTION_RUNTIME_FINGERPRINT_FILES
BoundedEnvIntFn = _bootstrap_module.BoundedEnvIntFn
GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainExtractionBundle = _bootstrap_module.Module2MainExtractionBundle
build_module2_main_extraction_bundle = _bootstrap_module.build_module2_main_extraction_bundle


__all__ = [
    "_EXTRACTION_RUNTIME_FINGERPRINT_FILES",
    "BoundedEnvIntFn",
    "GetEnvFn",
    "Module2MainExtractionBundle",
    "build_module2_main_extraction_bundle",
]
