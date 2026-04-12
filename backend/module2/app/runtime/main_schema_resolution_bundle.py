from __future__ import annotations

"""Compatibility shim for module2 main schema-resolution bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_resolution_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_resolution_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.schema import schema_resolution_builder as _bootstrap_module  # type: ignore[import-not-found]


SchemaTargetFieldsFn = _bootstrap_module.SchemaTargetFieldsFn
NormalizeSchemaFieldsFn = _bootstrap_module.NormalizeSchemaFieldsFn
SelectBestCanonicalSchemaFieldsFn = _bootstrap_module.SelectBestCanonicalSchemaFieldsFn
ApplyConservativeSemanticClosureFn = _bootstrap_module.ApplyConservativeSemanticClosureFn
UpsertSchemaFieldCandidateFn = _bootstrap_module.UpsertSchemaFieldCandidateFn
FilterAutoSchemaFieldsFn = _bootstrap_module.FilterAutoSchemaFieldsFn
InferSchemaFieldsLlmFn = _bootstrap_module.InferSchemaFieldsLlmFn
InferRuleBackedSchemaFieldsFn = _bootstrap_module.InferRuleBackedSchemaFieldsFn
InferSchemaFieldsHeuristicFn = _bootstrap_module.InferSchemaFieldsHeuristicFn
CanonicalizeSchemaFieldsFn = _bootstrap_module.CanonicalizeSchemaFieldsFn
NormalizeSchemaContractsFn = _bootstrap_module.NormalizeSchemaContractsFn
GetEnvFn = _bootstrap_module.GetEnvFn
Module2MainSchemaResolutionBundle = _bootstrap_module.Module2MainSchemaResolutionBundle
build_module2_main_schema_resolution_bundle = _bootstrap_module.build_module2_main_schema_resolution_bundle


__all__ = [
    "SchemaTargetFieldsFn",
    "NormalizeSchemaFieldsFn",
    "SelectBestCanonicalSchemaFieldsFn",
    "ApplyConservativeSemanticClosureFn",
    "UpsertSchemaFieldCandidateFn",
    "FilterAutoSchemaFieldsFn",
    "InferSchemaFieldsLlmFn",
    "InferRuleBackedSchemaFieldsFn",
    "InferSchemaFieldsHeuristicFn",
    "CanonicalizeSchemaFieldsFn",
    "NormalizeSchemaContractsFn",
    "GetEnvFn",
    "Module2MainSchemaResolutionBundle",
    "build_module2_main_schema_resolution_bundle",
]
