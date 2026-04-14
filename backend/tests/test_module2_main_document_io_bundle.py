from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_document_io_bundle_module = import_module("app.modules.module2.bootstrap.document_io")


class _FakeRect:
    def __init__(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.width = max(0.0, x2 - x1)
        self.height = max(0.0, y2 - y1)
        self.is_empty = self.width <= 0.0 or self.height <= 0.0

    def intersect(self, other: "_FakeRect") -> "_FakeRect":
        return _FakeRect(
            max(self.x1, other.x1),
            max(self.y1, other.y1),
            min(self.x2, other.x2),
            min(self.y2, other.y2),
        )


class _FakePixmap:
    def tobytes(self, fmt: str) -> bytes:
        assert fmt == "png"
        return b"fake-png"


class _FakePage:
    def __init__(self) -> None:
        self.rect = _FakeRect(0.0, 0.0, 200.0, 100.0)
        self.last_clip = None

    def get_pixmap(self, *, matrix, clip, alpha: bool):
        self.last_clip = clip
        assert alpha is False
        return _FakePixmap()


class _FakeDoc:
    def __init__(self) -> None:
        self.page_count = 1
        self.page = _FakePage()
        self.closed = False

    def load_page(self, index: int) -> _FakePage:
        assert index == 0
        return self.page

    def close(self) -> None:
        self.closed = True


class _FakeFitz:
    def __init__(self) -> None:
        self.last_doc = None
        self.last_matrix = None

    def open(self, *, stream: bytes, filetype: str) -> _FakeDoc:
        assert stream == b"%PDF"
        assert filetype == "pdf"
        self.last_doc = _FakeDoc()
        return self.last_doc

    def Rect(self, x1: float, y1: float, x2: float, y2: float) -> _FakeRect:
        return _FakeRect(x1, y1, x2, y2)

    def Matrix(self, x_zoom: float, y_zoom: float):
        self.last_matrix = (x_zoom, y_zoom)
        return self.last_matrix


def _build_bundle(*, fitz_module=None):
    return main_document_io_bundle_module.build_module2_main_document_io_bundle(
        is_meaningful_bbox=lambda bbox: bool(bbox) and len(bbox) >= 5,
        convert_word_bytes_to_pdf_fn=lambda **kwargs: (b"%PDF-converted", {"converter": "libreoffice", **kwargs}),
        convert_doc_bytes_to_docx_fn=lambda **kwargs: (b"docx-bytes", {"converter": "soffice", **kwargs}),
        load_fitz_module=(lambda: fitz_module) if fitz_module is not None else None,
    )


def test_build_module2_main_document_io_bundle_returns_none_for_non_meaningful_bbox() -> None:
    bundle = _build_bundle()

    out = bundle.crop_pdf_region_png(
        b"%PDF",
        [],
        144,
    )

    assert out is None


def test_module2_main_document_io_bundle_crops_pdf_region_png_with_normalized_bbox() -> None:
    fake_fitz = _FakeFitz()
    bundle = _build_bundle(fitz_module=fake_fitz)

    out = bundle.crop_pdf_region_png(
        b"%PDF",
        [1, 0.1, 0.2, 0.3, 0.4],
        144,
    )

    assert out == b"fake-png"
    assert fake_fitz.last_matrix == (2.0, 2.0)
    assert fake_fitz.last_doc is not None
    assert fake_fitz.last_doc.closed is True
    clip = fake_fitz.last_doc.page.last_clip
    assert round(clip.x1, 6) == 20.0
    assert round(clip.y1, 6) == 20.0
    assert round(clip.x2, 6) == 80.0
    assert round(clip.y2, 6) == 60.0


def test_module2_main_document_io_bundle_converts_word_to_pdf_with_timeout() -> None:
    bundle = _build_bundle()

    pdf_bytes, meta = asyncio.run(
        bundle.convert_word_to_pdf_with_timeout(
            file_name="demo.docx",
            file_bytes=b"word-bytes",
            timeout_sec=1.0,
        )
    )

    assert pdf_bytes == b"%PDF-converted"
    assert meta["converter"] == "libreoffice"
    assert meta["file_name"] == "demo.docx"


def test_module2_main_document_io_bundle_converts_doc_to_docx_with_timeout() -> None:
    bundle = _build_bundle()

    docx_bytes, meta = asyncio.run(
        bundle.convert_doc_to_docx_with_timeout(
            file_name="legacy.doc",
            file_bytes=b"doc-bytes",
            timeout_sec=1.0,
        )
    )

    assert docx_bytes == b"docx-bytes"
    assert meta["converter"] == "soffice"
    assert meta["file_name"] == "legacy.doc"
