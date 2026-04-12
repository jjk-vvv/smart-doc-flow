from __future__ import annotations

"""Compatibility adapter for schema-semantics builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_semantics_builder as _service_module
except ImportError:
    from module2.app.services.schema import schema_semantics_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
FieldNameWordTokensFn = _service_module.FieldNameWordTokensFn
CoerceFieldTypeFn = _service_module.CoerceFieldTypeFn
LooksLikeTitleFn = _service_module.LooksLikeTitleFn
LooksLikeSentenceFn = _service_module.LooksLikeSentenceFn
Module2MainSchemaSemanticsBundle = _service_module.Module2MainSchemaSemanticsBundle
build_module2_main_schema_semantics_bundle = _service_module.build_module2_main_schema_semantics_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "FieldNameWordTokensFn",
    "CoerceFieldTypeFn",
    "LooksLikeTitleFn",
    "LooksLikeSentenceFn",
    "Module2MainSchemaSemanticsBundle",
    "build_module2_main_schema_semantics_bundle",
]
