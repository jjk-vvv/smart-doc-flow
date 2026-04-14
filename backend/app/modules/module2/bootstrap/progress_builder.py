from __future__ import annotations

"""Compatibility adapter for progress builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import progress_builder as _service_module
except ImportError:
    from app.modules.module2.services.extraction import progress_builder as _service_module  # type: ignore[import-not-found]


GetEnvFn = _service_module.GetEnvFn
EmitProgressFn = _service_module.EmitProgressFn
_EXTRACTION_PROGRESS_STAGE_META = _service_module._EXTRACTION_PROGRESS_STAGE_META
Module2MainProgressBundle = _service_module.Module2MainProgressBundle
build_module2_main_progress_bundle = _service_module.build_module2_main_progress_bundle


__all__ = [
    "GetEnvFn",
    "EmitProgressFn",
    "_EXTRACTION_PROGRESS_STAGE_META",
    "Module2MainProgressBundle",
    "build_module2_main_progress_bundle",
]


