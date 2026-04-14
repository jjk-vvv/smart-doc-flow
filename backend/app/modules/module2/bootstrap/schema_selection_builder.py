from __future__ import annotations

"""Compatibility adapter for schema-selection builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_selection_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_selection_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
IsLowValueFieldNameFn = _service_module.IsLowValueFieldNameFn
SemanticClosureFragmentAliasKeysFn = _service_module.SemanticClosureFragmentAliasKeysFn
SchemaSemanticLabelStrengthFn = _service_module.SchemaSemanticLabelStrengthFn
IsSemanticallyWeakFieldLabelFn = _service_module.IsSemanticallyWeakFieldLabelFn
NormalizeFieldNameFn = _service_module.NormalizeFieldNameFn
CoerceFieldTypeFn = _service_module.CoerceFieldTypeFn
Module2MainSchemaSelectionBundle = _service_module.Module2MainSchemaSelectionBundle
build_module2_main_schema_selection_bundle = _service_module.build_module2_main_schema_selection_bundle


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


