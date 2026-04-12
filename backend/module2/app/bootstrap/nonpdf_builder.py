from __future__ import annotations

"""Compatibility adapter for nonpdf builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import nonpdf_builder as _service_module
except ImportError:
    from module2.app.services.extraction import nonpdf_builder as _service_module  # type: ignore[import-not-found]


GetEnvFn = _service_module.GetEnvFn
Module2MainNonPdfBundle = _service_module.Module2MainNonPdfBundle
build_module2_main_nonpdf_bundle = _service_module.build_module2_main_nonpdf_bundle


__all__ = [
    "GetEnvFn",
    "Module2MainNonPdfBundle",
    "build_module2_main_nonpdf_bundle",
]
