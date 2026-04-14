from __future__ import annotations

"""Compatibility shim for module2 main schema-primitives bundle builders.

The canonical implementation has moved to
``module2.app.services.schema.schema_primitives_builder`` as part of layered migration.
This module intentionally re-exports the same symbols to keep legacy imports
stable.
"""

try:
    from ..services.schema import schema_primitives_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from app.modules.module2.services.schema import schema_primitives_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainSchemaPrimitivesBundle = _bootstrap_module.Module2MainSchemaPrimitivesBundle
build_module2_main_schema_primitives_bundle = _bootstrap_module.build_module2_main_schema_primitives_bundle
SchemaTargetFieldsFn = _bootstrap_module.SchemaTargetFieldsFn
NormalizeSchemaFieldsFn = _bootstrap_module.NormalizeSchemaFieldsFn
GetEnvFn = _bootstrap_module.GetEnvFn
IsWordFileFn = _bootstrap_module.IsWordFileFn
SchemaContextCleanTextFn = _bootstrap_module.SchemaContextCleanTextFn
CountTableCellsFn = _bootstrap_module.CountTableCellsFn
CountFigureDataframeCellsFn = _bootstrap_module.CountFigureDataframeCellsFn
Module2MainSchemaRequestBundle = _bootstrap_module.Module2MainSchemaRequestBundle
build_module2_main_schema_request_bundle = _bootstrap_module.build_module2_main_schema_request_bundle
Module2MainSchemaTimeoutBundle = _bootstrap_module.Module2MainSchemaTimeoutBundle
build_module2_main_schema_timeout_bundle = _bootstrap_module.build_module2_main_schema_timeout_bundle


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

