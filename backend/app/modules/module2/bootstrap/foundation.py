"""Compatibility adapter for Module2 bootstrap foundation entrypoints.

Canonical composition entrypoints live in ``module2.app.composition.foundation``.
"""

from ..composition.foundation import (
    GetEnvFn,
    Module2BootstrapComponents,
    Module2MainFoundationBundle,
    build_module2_default_bootstrap_components,
    build_module2_main_foundation_bundle,
)

__all__ = [
    "GetEnvFn",
    "Module2BootstrapComponents",
    "Module2MainFoundationBundle",
    "build_module2_default_bootstrap_components",
    "build_module2_main_foundation_bundle",
]
