from __future__ import annotations

"""Compatibility shim for module2 main schema-fields bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_fields_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_fields_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.schema import schema_fields_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
CoerceFieldTypeFn = _bootstrap_module.CoerceFieldTypeFn
SchemaFieldTypePriorityFn = _bootstrap_module.SchemaFieldTypePriorityFn
SchemaFieldTypeHintFn = _bootstrap_module.SchemaFieldTypeHintFn
Module2MainSchemaFieldsBundle = _bootstrap_module.Module2MainSchemaFieldsBundle
build_module2_main_schema_fields_bundle = _bootstrap_module.build_module2_main_schema_fields_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "CoerceFieldTypeFn",
    "SchemaFieldTypePriorityFn",
    "SchemaFieldTypeHintFn",
    "Module2MainSchemaFieldsBundle",
    "build_module2_main_schema_fields_bundle",
]
