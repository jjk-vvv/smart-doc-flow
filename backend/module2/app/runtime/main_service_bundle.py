from __future__ import annotations

"""Compatibility shim for module2 main service bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.service_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import service_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import service_builder as _bootstrap_module  # type: ignore[import-not-found]


ArtifactRootFactory = _bootstrap_module.ArtifactRootFactory
ConvertWordToPdfFn = _bootstrap_module.ConvertWordToPdfFn
TimeoutSecFactory = _bootstrap_module.TimeoutSecFactory
NormalizeBboxFn = _bootstrap_module.NormalizeBboxFn
PageFromBboxFn = _bootstrap_module.PageFromBboxFn
IsMeaningfulBboxFn = _bootstrap_module.IsMeaningfulBboxFn
UtcNowFactory = _bootstrap_module.UtcNowFactory
Module2MainServiceBundle = _bootstrap_module.Module2MainServiceBundle
build_module2_main_service_bundle = _bootstrap_module.build_module2_main_service_bundle


__all__ = [
    "ArtifactRootFactory",
    "ConvertWordToPdfFn",
    "TimeoutSecFactory",
    "NormalizeBboxFn",
    "PageFromBboxFn",
    "IsMeaningfulBboxFn",
    "UtcNowFactory",
    "Module2MainServiceBundle",
    "build_module2_main_service_bundle",
]
