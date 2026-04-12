from __future__ import annotations

"""Compatibility shim for module2 main entry bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.entry_builder`` and is exposed through the
bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import entry_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import entry_builder as _bootstrap_module  # type: ignore[import-not-found]


Module2MainEntryBundle = _bootstrap_module.Module2MainEntryBundle
build_module2_main_entry_bundle = _bootstrap_module.build_module2_main_entry_bundle


__all__ = [
    "Module2MainEntryBundle",
    "build_module2_main_entry_bundle",
]
