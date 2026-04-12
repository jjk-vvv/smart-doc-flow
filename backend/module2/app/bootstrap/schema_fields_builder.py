from __future__ import annotations

"""Compatibility adapter for schema-fields builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_fields_builder as _service_module
except ImportError:
    from module2.app.services.schema import schema_fields_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
CoerceFieldTypeFn = _service_module.CoerceFieldTypeFn
SchemaFieldTypePriorityFn = _service_module.SchemaFieldTypePriorityFn
SchemaFieldTypeHintFn = _service_module.SchemaFieldTypeHintFn
Module2MainSchemaFieldsBundle = _service_module.Module2MainSchemaFieldsBundle
build_module2_main_schema_fields_bundle = _service_module.build_module2_main_schema_fields_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "CoerceFieldTypeFn",
    "SchemaFieldTypePriorityFn",
    "SchemaFieldTypeHintFn",
    "Module2MainSchemaFieldsBundle",
    "build_module2_main_schema_fields_bundle",
]
