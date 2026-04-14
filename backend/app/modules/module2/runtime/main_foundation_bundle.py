from __future__ import annotations

"""Compatibility shim for module2 main foundation bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.foundation_builder`` and is exposed through
the bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..composition import foundation as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.composition import foundation as _bootstrap_module  # type: ignore[import-not-found]


GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainFoundationBundle = _bootstrap_module.Module2MainFoundationBundle
Module2BootstrapComponents = _bootstrap_module.Module2BootstrapComponents
build_module2_main_foundation_bundle = _bootstrap_module.build_module2_main_foundation_bundle
build_module2_default_bootstrap_components = _bootstrap_module.build_module2_default_bootstrap_components


__all__ = [
    "GetEnvFn",
    "Module2MainFoundationBundle",
    "Module2BootstrapComponents",
    "build_module2_main_foundation_bundle",
    "build_module2_default_bootstrap_components",
]

