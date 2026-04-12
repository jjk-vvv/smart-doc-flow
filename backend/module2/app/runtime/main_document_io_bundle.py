from __future__ import annotations

"""Compatibility shim for module2 main document-io bundle builders.

The canonical implementation lives in
``module2.app.services.extraction.document_io_builder`` and is exposed through
the bootstrap adapter. This module intentionally re-exports the same symbols to
keep legacy imports stable.
"""

try:
    from ..services.extraction import document_io_builder as _bootstrap_module
except ImportError:
    # Loaded as a standalone file in some tests (no package context).
    from module2.app.services.extraction import document_io_builder as _bootstrap_module  # type: ignore[import-not-found]


IsMeaningfulBboxFn = _bootstrap_module.IsMeaningfulBboxFn
ConvertWordBytesToPdfFn = _bootstrap_module.ConvertWordBytesToPdfFn
ConvertDocBytesToDocxFn = _bootstrap_module.ConvertDocBytesToDocxFn
LoadFitzModuleFn = _bootstrap_module.LoadFitzModuleFn
Module2MainDocumentIoBundle = _bootstrap_module.Module2MainDocumentIoBundle
build_module2_main_document_io_bundle = _bootstrap_module.build_module2_main_document_io_bundle


__all__ = [
    "IsMeaningfulBboxFn",
    "ConvertWordBytesToPdfFn",
    "ConvertDocBytesToDocxFn",
    "LoadFitzModuleFn",
    "Module2MainDocumentIoBundle",
    "build_module2_main_document_io_bundle",
]
