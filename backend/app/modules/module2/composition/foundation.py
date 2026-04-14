from __future__ import annotations

"""Canonical composition entrypoints for Module2 application assembly."""

from ..services.extraction.foundation_builder import (
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
