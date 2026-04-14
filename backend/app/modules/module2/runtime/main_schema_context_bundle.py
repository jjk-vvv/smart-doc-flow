from __future__ import annotations

"""Compatibility shim for module2 main schema-context bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_context_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_context_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import schema_context_builder as _bootstrap_module  # type: ignore[import-not-found]


SanitizeFieldNameFn = _bootstrap_module.SanitizeFieldNameFn
Module2MainSchemaContextBundle = _bootstrap_module.Module2MainSchemaContextBundle
build_module2_main_schema_context_bundle = _bootstrap_module.build_module2_main_schema_context_bundle


__all__ = [
    "SanitizeFieldNameFn",
    "Module2MainSchemaContextBundle",
    "build_module2_main_schema_context_bundle",
]

