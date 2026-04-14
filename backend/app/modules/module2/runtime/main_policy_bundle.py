from __future__ import annotations

"""Compatibility shim for module2 main policy bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.policy_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import policy_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.extraction import policy_builder as _bootstrap_module  # type: ignore[import-not-found]


GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainPolicyBundle = _bootstrap_module.Module2MainPolicyBundle
build_module2_main_policy_bundle = _bootstrap_module.build_module2_main_policy_bundle


__all__ = [
    "GetEnvFn",
    "Module2MainPolicyBundle",
    "build_module2_main_policy_bundle",
]

