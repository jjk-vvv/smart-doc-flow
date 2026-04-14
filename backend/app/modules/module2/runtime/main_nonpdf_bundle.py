from __future__ import annotations

"""Compatibility shim for module2 main nonpdf bundle builders.

The canonical implementation has moved to
``module2.app.services.extraction.nonpdf_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.extraction import nonpdf_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.extraction import nonpdf_builder as _bootstrap_module  # type: ignore[import-not-found]


GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainNonPdfBundle = _bootstrap_module.Module2MainNonPdfBundle
build_module2_main_nonpdf_bundle = _bootstrap_module.build_module2_main_nonpdf_bundle


__all__ = [
    "GetEnvFn",
    "Module2MainNonPdfBundle",
    "build_module2_main_nonpdf_bundle",
]

