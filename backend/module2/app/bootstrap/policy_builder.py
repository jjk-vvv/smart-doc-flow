from __future__ import annotations

"""Compatibility adapter for policy builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import policy_builder as _service_module
except ImportError:
    from module2.app.services.extraction import policy_builder as _service_module  # type: ignore[import-not-found]


GetEnvFn = _service_module.GetEnvFn
Module2MainPolicyBundle = _service_module.Module2MainPolicyBundle
build_module2_main_policy_bundle = _service_module.build_module2_main_policy_bundle


__all__ = [
    "GetEnvFn",
    "Module2MainPolicyBundle",
    "build_module2_main_policy_bundle",
]
