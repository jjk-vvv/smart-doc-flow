from __future__ import annotations

"""Compatibility adapter for schema-LLM builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_llm_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_llm_builder as _service_module  # type: ignore[import-not-found]


GetEnvFn = _service_module.GetEnvFn
ExtractTextForSchemaFn = _service_module.ExtractTextForSchemaFn
UpsertSchemaFieldCandidateFn = _service_module.UpsertSchemaFieldCandidateFn
FilterAutoSchemaFieldsFn = _service_module.FilterAutoSchemaFieldsFn
Module2MainSchemaLlmBundle = _service_module.Module2MainSchemaLlmBundle
build_module2_main_schema_llm_bundle = _service_module.build_module2_main_schema_llm_bundle


__all__ = [
    "GetEnvFn",
    "ExtractTextForSchemaFn",
    "UpsertSchemaFieldCandidateFn",
    "FilterAutoSchemaFieldsFn",
    "Module2MainSchemaLlmBundle",
    "build_module2_main_schema_llm_bundle",
]


