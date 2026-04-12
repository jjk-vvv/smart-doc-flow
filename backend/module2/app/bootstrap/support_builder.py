from __future__ import annotations

"""Compatibility adapter for support builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import support_builder as _service_module
except ImportError:
    from module2.app.services.extraction import support_builder as _service_module  # type: ignore[import-not-found]


Module2MainSupportBundle = _service_module.Module2MainSupportBundle
Module2BootstrapRuntimeBundle = _service_module.Module2BootstrapRuntimeBundle
build_module2_main_support_bundle = _service_module.build_module2_main_support_bundle
build_module2_bootstrap_runtime_bundle = _service_module.build_module2_bootstrap_runtime_bundle


__all__ = [
    "Module2MainSupportBundle",
    "Module2BootstrapRuntimeBundle",
    "build_module2_main_support_bundle",
    "build_module2_bootstrap_runtime_bundle",
]
