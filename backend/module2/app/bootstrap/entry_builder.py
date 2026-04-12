from __future__ import annotations

"""Compatibility adapter for entry builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import entry_builder as _service_module
except ImportError:
    from module2.app.services.extraction import entry_builder as _service_module  # type: ignore[import-not-found]


Module2MainEntryBundle = _service_module.Module2MainEntryBundle
build_module2_main_entry_bundle = _service_module.build_module2_main_entry_bundle


__all__ = [
    "Module2MainEntryBundle",
    "build_module2_main_entry_bundle",
]
