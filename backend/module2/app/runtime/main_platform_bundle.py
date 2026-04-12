from __future__ import annotations

"""Compatibility shim for module2 main platform bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.platform_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import platform_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import platform_builder as _bootstrap_module  # type: ignore[import-not-found]


BuildPoolFn = _bootstrap_module.BuildPoolFn
ParseDocumentInSubprocessFn = _bootstrap_module.ParseDocumentInSubprocessFn
GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainPlatformBundle = _bootstrap_module.Module2MainPlatformBundle
build_module2_main_platform_bundle = _bootstrap_module.build_module2_main_platform_bundle


__all__ = [
    "BuildPoolFn",
    "ParseDocumentInSubprocessFn",
    "GetEnvFn",
    "Module2MainPlatformBundle",
    "build_module2_main_platform_bundle",
]
