from __future__ import annotations

"""Compatibility shim for module2 main support bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.support_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import support_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import support_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainSupportBundle = _bootstrap_module.Module2MainSupportBundle
Module2BootstrapRuntimeBundle = _bootstrap_module.Module2BootstrapRuntimeBundle
build_module2_main_support_bundle = _bootstrap_module.build_module2_main_support_bundle
build_module2_bootstrap_runtime_bundle = _bootstrap_module.build_module2_bootstrap_runtime_bundle


__all__ = [
    "Module2MainSupportBundle",
    "Module2BootstrapRuntimeBundle",
    "build_module2_main_support_bundle",
    "build_module2_bootstrap_runtime_bundle",
]
