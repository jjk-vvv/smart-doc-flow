from __future__ import annotations

"""Compatibility shim for module2 main workflow bundle builders.

The canonical implementation has moved to
``module2.app.services.extraction.workflow_builder`` as part of layered
migration. This module intentionally re-exports the same symbols to keep
legacy imports stable.
"""

try:
    from ..services.extraction import workflow_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import workflow_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainWorkflowBundle = _bootstrap_module.Module2MainWorkflowBundle
build_module2_main_workflow_bundle = _bootstrap_module.build_module2_main_workflow_bundle


__all__ = [
    "Module2MainWorkflowBundle",
    "build_module2_main_workflow_bundle",
]
