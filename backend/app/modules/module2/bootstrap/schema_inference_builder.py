from __future__ import annotations

"""Compatibility adapter for schema-inference builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_inference_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_inference_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _service_module.IsLowValueFieldNameFn
FilterAutoSchemaFieldsFn = _service_module.FilterAutoSchemaFieldsFn
SchemaFieldTypePriorityFn = _service_module.SchemaFieldTypePriorityFn
SchemaContextCleanTextFn = _service_module.SchemaContextCleanTextFn
LooksLikeTitleFn = _service_module.LooksLikeTitleFn
LooksLikeSentenceFn = _service_module.LooksLikeSentenceFn
Module2MainSchemaInferenceBundle = _service_module.Module2MainSchemaInferenceBundle
build_module2_main_schema_inference_bundle = _service_module.build_module2_main_schema_inference_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "IsLowValueFieldNameFn",
    "FilterAutoSchemaFieldsFn",
    "SchemaFieldTypePriorityFn",
    "SchemaContextCleanTextFn",
    "LooksLikeTitleFn",
    "LooksLikeSentenceFn",
    "Module2MainSchemaInferenceBundle",
    "build_module2_main_schema_inference_bundle",
]


