from __future__ import annotations

"""Compatibility adapter for schema-primitives builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.schema``.
"""

try:
    from ..services.schema import schema_primitives_builder as _service_module
except ImportError:
    from app.modules.module2.services.schema import schema_primitives_builder as _service_module  # type: ignore[import-not-found]


Module2MainSchemaPrimitivesBundle = _service_module.Module2MainSchemaPrimitivesBundle
build_module2_main_schema_primitives_bundle = _service_module.build_module2_main_schema_primitives_bundle
SchemaTargetFieldsFn = _service_module.SchemaTargetFieldsFn
NormalizeSchemaFieldsFn = _service_module.NormalizeSchemaFieldsFn
GetEnvFn = _service_module.GetEnvFn
IsWordFileFn = _service_module.IsWordFileFn
SchemaContextCleanTextFn = _service_module.SchemaContextCleanTextFn
CountTableCellsFn = _service_module.CountTableCellsFn
CountFigureDataframeCellsFn = _service_module.CountFigureDataframeCellsFn
Module2MainSchemaRequestBundle = _service_module.Module2MainSchemaRequestBundle
build_module2_main_schema_request_bundle = _service_module.build_module2_main_schema_request_bundle
Module2MainSchemaTimeoutBundle = _service_module.Module2MainSchemaTimeoutBundle
build_module2_main_schema_timeout_bundle = _service_module.build_module2_main_schema_timeout_bundle


__all__ = [
    "Module2MainSchemaPrimitivesBundle",
    "build_module2_main_schema_primitives_bundle",
    "SchemaTargetFieldsFn",
    "NormalizeSchemaFieldsFn",
    "GetEnvFn",
    "IsWordFileFn",
    "SchemaContextCleanTextFn",
    "CountTableCellsFn",
    "CountFigureDataframeCellsFn",
    "Module2MainSchemaRequestBundle",
    "build_module2_main_schema_request_bundle",
    "Module2MainSchemaTimeoutBundle",
    "build_module2_main_schema_timeout_bundle",
]


