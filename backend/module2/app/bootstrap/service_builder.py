from __future__ import annotations

"""Compatibility adapter for service builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import service_builder as _service_module
except ImportError:
    from module2.app.services.extraction import service_builder as _service_module  # type: ignore[import-not-found]


ArtifactRootFactory = _service_module.ArtifactRootFactory
ConvertWordToPdfFn = _service_module.ConvertWordToPdfFn
TimeoutSecFactory = _service_module.TimeoutSecFactory
NormalizeBboxFn = _service_module.NormalizeBboxFn
PageFromBboxFn = _service_module.PageFromBboxFn
IsMeaningfulBboxFn = _service_module.IsMeaningfulBboxFn
UtcNowFactory = _service_module.UtcNowFactory
Module2MainServiceBundle = _service_module.Module2MainServiceBundle
build_module2_main_service_bundle = _service_module.build_module2_main_service_bundle


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
