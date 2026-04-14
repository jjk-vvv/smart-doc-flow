"""Parser runtime exports for module2."""

from .native_document_parser import NativeDocumentParser, parse_document_in_subprocess

__all__ = [
    "NativeDocumentParser",
    "parse_document_in_subprocess",
]
