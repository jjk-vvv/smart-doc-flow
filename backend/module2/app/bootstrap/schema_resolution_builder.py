from __future__ import annotations

"""Compatibility adapter for schema-resolution builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_resolution_builder as _service_module
except ImportError:
    from module2.app.services.schema import schema_resolution_builder as _service_module  # type: ignore[import-not-found]


SchemaTargetFieldsFn = _service_module.SchemaTargetFieldsFn
NormalizeSchemaFieldsFn = _service_module.NormalizeSchemaFieldsFn
SelectBestCanonicalSchemaFieldsFn = _service_module.SelectBestCanonicalSchemaFieldsFn
ApplyConservativeSemanticClosureFn = _service_module.ApplyConservativeSemanticClosureFn
UpsertSchemaFieldCandidateFn = _service_module.UpsertSchemaFieldCandidateFn
FilterAutoSchemaFieldsFn = _service_module.FilterAutoSchemaFieldsFn
InferSchemaFieldsLlmFn = _service_module.InferSchemaFieldsLlmFn
InferRuleBackedSchemaFieldsFn = _service_module.InferRuleBackedSchemaFieldsFn
InferSchemaFieldsHeuristicFn = _service_module.InferSchemaFieldsHeuristicFn
CanonicalizeSchemaFieldsFn = _service_module.CanonicalizeSchemaFieldsFn
NormalizeSchemaContractsFn = _service_module.NormalizeSchemaContractsFn
GetEnvFn = _service_module.GetEnvFn
Module2MainSchemaResolutionBundle = _service_module.Module2MainSchemaResolutionBundle
build_module2_main_schema_resolution_bundle = _service_module.build_module2_main_schema_resolution_bundle


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
