from __future__ import annotations

"""Compatibility shim for module2 main schema-inference bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_inference_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_inference_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.schema import schema_inference_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _bootstrap_module.IsLowValueFieldNameFn
FilterAutoSchemaFieldsFn = _bootstrap_module.FilterAutoSchemaFieldsFn
SchemaFieldTypePriorityFn = _bootstrap_module.SchemaFieldTypePriorityFn
SchemaContextCleanTextFn = _bootstrap_module.SchemaContextCleanTextFn
LooksLikeTitleFn = _bootstrap_module.LooksLikeTitleFn
LooksLikeSentenceFn = _bootstrap_module.LooksLikeSentenceFn
Module2MainSchemaInferenceBundle = _bootstrap_module.Module2MainSchemaInferenceBundle
build_module2_main_schema_inference_bundle = _bootstrap_module.build_module2_main_schema_inference_bundle


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
