from __future__ import annotations

"""Compatibility adapter for schema-pipeline builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_pipeline_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_pipeline_builder as _service_module  # type: ignore[import-not-found]


Module2MainSchemaPipelineBundle = _service_module.Module2MainSchemaPipelineBundle
build_module2_main_schema_pipeline_bundle = _service_module.build_module2_main_schema_pipeline_bundle
build_module2_main_schema_pipeline_bundle_from_rules = (
    _service_module.build_module2_main_schema_pipeline_bundle_from_rules
)


__all__ = [
    "Module2MainSchemaPipelineBundle",
    "build_module2_main_schema_pipeline_bundle",
    "build_module2_main_schema_pipeline_bundle_from_rules",
]


