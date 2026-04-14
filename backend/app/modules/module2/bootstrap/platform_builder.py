from __future__ import annotations

"""Compatibility adapter for platform builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import platform_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import platform_builder as _service_module  # type: ignore[import-not-found]


BuildPoolFn = _service_module.BuildPoolFn
ParseDocumentInSubprocessFn = _service_module.ParseDocumentInSubprocessFn
GetEnvFn = _service_module.GetEnvFn
Module2MainPlatformBundle = _service_module.Module2MainPlatformBundle
build_module2_main_platform_bundle = _service_module.build_module2_main_platform_bundle


__all__ = [
    "BuildPoolFn",
    "ParseDocumentInSubprocessFn",
    "GetEnvFn",
    "Module2MainPlatformBundle",
    "build_module2_main_platform_bundle",
]


