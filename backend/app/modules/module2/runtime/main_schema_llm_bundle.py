from __future__ import annotations

"""Compatibility shim for module2 main schema-LLM bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_llm_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_llm_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import schema_llm_builder as _bootstrap_module  # type: ignore[import-not-found]


GetEnvFn = _bootstrap_module.GetEnvFn
ExtractTextForSchemaFn = _bootstrap_module.ExtractTextForSchemaFn
UpsertSchemaFieldCandidateFn = _bootstrap_module.UpsertSchemaFieldCandidateFn
FilterAutoSchemaFieldsFn = _bootstrap_module.FilterAutoSchemaFieldsFn
Module2MainSchemaLlmBundle = _bootstrap_module.Module2MainSchemaLlmBundle
build_module2_main_schema_llm_bundle = _bootstrap_module.build_module2_main_schema_llm_bundle


__all__ = [
    "GetEnvFn",
    "ExtractTextForSchemaFn",
    "UpsertSchemaFieldCandidateFn",
    "FilterAutoSchemaFieldsFn",
    "Module2MainSchemaLlmBundle",
    "build_module2_main_schema_llm_bundle",
]

