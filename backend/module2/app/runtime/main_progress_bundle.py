from __future__ import annotations

"""Compatibility shim for module2 main progress bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.progress_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import progress_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import progress_builder as _bootstrap_module  # type: ignore[import-not-found]


GetEnvFn = _bootstrap_module.GetEnvFn
EmitProgressFn = _bootstrap_module.EmitProgressFn
_EXTRACTION_PROGRESS_STAGE_META = _bootstrap_module._EXTRACTION_PROGRESS_STAGE_META
Module2MainProgressBundle = _bootstrap_module.Module2MainProgressBundle
build_module2_main_progress_bundle = _bootstrap_module.build_module2_main_progress_bundle


__all__ = [
    "GetEnvFn",
    "EmitProgressFn",
    "_EXTRACTION_PROGRESS_STAGE_META",
    "Module2MainProgressBundle",
    "build_module2_main_progress_bundle",
]
