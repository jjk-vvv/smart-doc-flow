from __future__ import annotations

"""Compatibility adapter for foundation builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import foundation_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import foundation_builder as _service_module  # type: ignore[import-not-found]


GetEnvFn = _service_module.GetEnvFn
Module2MainFoundationBundle = _service_module.Module2MainFoundationBundle
Module2BootstrapComponents = _service_module.Module2BootstrapComponents
build_module2_main_foundation_bundle = _service_module.build_module2_main_foundation_bundle
build_module2_default_bootstrap_components = _service_module.build_module2_default_bootstrap_components


__all__ = [
    "GetEnvFn",
    "Module2MainFoundationBundle",
    "Module2BootstrapComponents",
    "build_module2_main_foundation_bundle",
    "build_module2_default_bootstrap_components",
]


