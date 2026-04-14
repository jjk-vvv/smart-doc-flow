from __future__ import annotations

"""Compatibility adapter for schema-context builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_context_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_context_builder as _service_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _service_module.SanitizeFieldNameFn
Module2MainSchemaContextBundle = _service_module.Module2MainSchemaContextBundle
build_module2_main_schema_context_bundle = _service_module.build_module2_main_schema_context_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "Module2MainSchemaContextBundle",
    "build_module2_main_schema_context_bundle",
]


