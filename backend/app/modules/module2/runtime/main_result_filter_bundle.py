from __future__ import annotations

"""Compatibility shim for module2 main result-filter bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.result_filter_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import result_filter_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import result_filter_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _bootstrap_module.IsLowValueFieldNameFn
ShouldPruneShadowedFieldNameFn = _bootstrap_module.ShouldPruneShadowedFieldNameFn
ToNumberOrNoneFn = _bootstrap_module.ToNumberOrNoneFn
Module2MainResultFilterBundle = _bootstrap_module.Module2MainResultFilterBundle
build_module2_main_result_filter_bundle = _bootstrap_module.build_module2_main_result_filter_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "IsLowValueFieldNameFn",
    "ShouldPruneShadowedFieldNameFn",
    "ToNumberOrNoneFn",
    "Module2MainResultFilterBundle",
    "build_module2_main_result_filter_bundle",
]

