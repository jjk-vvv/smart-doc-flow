from __future__ import annotations

"""Compatibility adapter for quick-extract builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import quick_extract_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import quick_extract_builder as _service_module  # type: ignore[import-not-found]


IsLowValueFieldNameFn = _service_module.IsLowValueFieldNameFn
CoerceFieldTypeFn = _service_module.CoerceFieldTypeFn
IsLowValueFallbackValueFn = _service_module.IsLowValueFallbackValueFn
NormalizeBboxFn = _service_module.NormalizeBboxFn
ToNumberOrNoneFn = _service_module.ToNumberOrNoneFn
Module2MainQuickExtractBundle = _service_module.Module2MainQuickExtractBundle
Module2MainValueGuardBundle = _service_module.Module2MainValueGuardBundle
build_module2_main_value_guard_bundle = _service_module.build_module2_main_value_guard_bundle
build_module2_main_quick_extract_bundle = _service_module.build_module2_main_quick_extract_bundle


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


