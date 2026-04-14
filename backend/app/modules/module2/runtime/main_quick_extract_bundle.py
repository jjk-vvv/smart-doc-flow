from __future__ import annotations

"""Compatibility shim for module2 main quick-extract bundle builders.

The canonical implementation has moved to
``module2.app.services.extraction.quick_extract_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.extraction import quick_extract_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.extraction import quick_extract_builder as _bootstrap_module  # type: ignore[import-not-found]


IsLowValueFieldNameFn = _bootstrap_module.IsLowValueFieldNameFn
CoerceFieldTypeFn = _bootstrap_module.CoerceFieldTypeFn
IsLowValueFallbackValueFn = _bootstrap_module.IsLowValueFallbackValueFn
NormalizeBboxFn = _bootstrap_module.NormalizeBboxFn
ToNumberOrNoneFn = _bootstrap_module.ToNumberOrNoneFn
Module2MainQuickExtractBundle = _bootstrap_module.Module2MainQuickExtractBundle
Module2MainValueGuardBundle = _bootstrap_module.Module2MainValueGuardBundle
build_module2_main_value_guard_bundle = _bootstrap_module.build_module2_main_value_guard_bundle
build_module2_main_quick_extract_bundle = _bootstrap_module.build_module2_main_quick_extract_bundle


__all__ = [
    "IsLowValueFieldNameFn",
    "CoerceFieldTypeFn",
    "IsLowValueFallbackValueFn",
    "NormalizeBboxFn",
    "ToNumberOrNoneFn",
    "Module2MainQuickExtractBundle",
    "Module2MainValueGuardBundle",
    "build_module2_main_value_guard_bundle",
    "build_module2_main_quick_extract_bundle",
]

