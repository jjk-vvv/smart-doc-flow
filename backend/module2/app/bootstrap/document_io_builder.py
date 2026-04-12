from __future__ import annotations

"""Compatibility adapter for document-io builder in bootstrap layer.

Canonical implementation lives in ``module2.app.services.extraction``.
"""

try:
    from ..services.extraction import document_io_builder as _service_module
except ImportError:
    from module2.app.services.extraction import document_io_builder as _service_module  # type: ignore[import-not-found]


IsMeaningfulBboxFn = _service_module.IsMeaningfulBboxFn
ConvertWordBytesToPdfFn = _service_module.ConvertWordBytesToPdfFn
ConvertDocBytesToDocxFn = _service_module.ConvertDocBytesToDocxFn
LoadFitzModuleFn = _service_module.LoadFitzModuleFn
Module2MainDocumentIoBundle = _service_module.Module2MainDocumentIoBundle
build_module2_main_document_io_bundle = _service_module.build_module2_main_document_io_bundle


__all__ = [
    "IsMeaningfulBboxFn",
    "ConvertWordBytesToPdfFn",
    "ConvertDocBytesToDocxFn",
    "LoadFitzModuleFn",
    "Module2MainDocumentIoBundle",
    "build_module2_main_document_io_bundle",
]
