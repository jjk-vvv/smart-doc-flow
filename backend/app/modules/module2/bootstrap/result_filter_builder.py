from __future__ import annotations

"""Compatibility adapter for result-filter builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import result_filter_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import result_filter_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _service_module.IsLowValueFieldNameFn
ShouldPruneShadowedFieldNameFn = _service_module.ShouldPruneShadowedFieldNameFn
ToNumberOrNoneFn = _service_module.ToNumberOrNoneFn
Module2MainResultFilterBundle = _service_module.Module2MainResultFilterBundle
build_module2_main_result_filter_bundle = _service_module.build_module2_main_result_filter_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "IsLowValueFieldNameFn",
    "ShouldPruneShadowedFieldNameFn",
    "ToNumberOrNoneFn",
    "Module2MainResultFilterBundle",
    "build_module2_main_result_filter_bundle",
]


