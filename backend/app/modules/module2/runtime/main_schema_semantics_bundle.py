from __future__ import annotations

"""Compatibility shim for module2 main schema-semantics bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_semantics_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_semantics_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import schema_semantics_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
FieldNameWordTokensFn = _bootstrap_module.FieldNameWordTokensFn
CoerceFieldTypeFn = _bootstrap_module.CoerceFieldTypeFn
LooksLikeTitleFn = _bootstrap_module.LooksLikeTitleFn
LooksLikeSentenceFn = _bootstrap_module.LooksLikeSentenceFn
Module2MainSchemaSemanticsBundle = _bootstrap_module.Module2MainSchemaSemanticsBundle
build_module2_main_schema_semantics_bundle = _bootstrap_module.build_module2_main_schema_semantics_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "FieldNameWordTokensFn",
    "CoerceFieldTypeFn",
    "LooksLikeTitleFn",
    "LooksLikeSentenceFn",
    "Module2MainSchemaSemanticsBundle",
    "build_module2_main_schema_semantics_bundle",
]

