from __future__ import annotations

"""Compatibility shim for module2 main schema-pipeline bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_pipeline_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_pipeline_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import schema_pipeline_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainSchemaPipelineBundle = _bootstrap_module.Module2MainSchemaPipelineBundle
build_module2_main_schema_pipeline_bundle = _bootstrap_module.build_module2_main_schema_pipeline_bundle
build_module2_main_schema_pipeline_bundle_from_rules = (
    _bootstrap_module.build_module2_main_schema_pipeline_bundle_from_rules
)


__all__ = [
    "Module2MainSchemaPipelineBundle",
    "build_module2_main_schema_pipeline_bundle",
    "build_module2_main_schema_pipeline_bundle_from_rules",
]

