from __future__ import annotations

"""Compatibility shim for module2 main schema-selection bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_selection_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_selection_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.schema import schema_selection_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _bootstrap_module.IsLowValueFieldNameFn
SemanticClosureFragmentAliasKeysFn = _bootstrap_module.SemanticClosureFragmentAliasKeysFn
SchemaSemanticLabelStrengthFn = _bootstrap_module.SchemaSemanticLabelStrengthFn
IsSemanticallyWeakFieldLabelFn = _bootstrap_module.IsSemanticallyWeakFieldLabelFn
NormalizeFieldNameFn = _bootstrap_module.NormalizeFieldNameFn
CoerceFieldTypeFn = _bootstrap_module.CoerceFieldTypeFn
Module2MainSchemaSelectionBundle = _bootstrap_module.Module2MainSchemaSelectionBundle
build_module2_main_schema_selection_bundle = _bootstrap_module.build_module2_main_schema_selection_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "IsLowValueFieldNameFn",
    "SemanticClosureFragmentAliasKeysFn",
    "SchemaSemanticLabelStrengthFn",
    "IsSemanticallyWeakFieldLabelFn",
    "NormalizeFieldNameFn",
    "CoerceFieldTypeFn",
    "Module2MainSchemaSelectionBundle",
    "build_module2_main_schema_selection_bundle",
]
