from __future__ import annotations

"""Document I/O bundle builders for module2 extraction service layer."""

import asyncio
from dataclasses import dataclass
import importlib
from typing import Any, Callable, Dict, List, Optional, Tuple


IsMeaningfulBboxFn = Callable[[Any], bool]
ConvertWordBytesToPdfFn = Callable[..., Tuple[bytes, Dict[str, Any]]]
ConvertDocBytesToDocxFn = Callable[..., Tuple[bytes, Dict[str, Any]]]
LoadFitzModuleFn = Callable[[], Any]


@dataclass(frozen=True)
class Module2MainDocumentIoBundle:
    crop_pdf_region_png: Callable[[bytes, List[float], int], Optional[bytes]]
    convert_word_to_pdf_with_timeout: Callable[..., Any]
    convert_doc_to_docx_with_timeout: Callable[..., Any]


def build_module2_main_document_io_bundle(
    *,
    is_meaningful_bbox: IsMeaningfulBboxFn,
    convert_word_bytes_to_pdf_fn: ConvertWordBytesToPdfFn,
    convert_doc_bytes_to_docx_fn: ConvertDocBytesToDocxFn,
    load_fitz_module: LoadFitzModuleFn | None = None,
) -> Module2MainDocumentIoBundle:
    def _load_fitz_module() -> Any:
        if load_fitz_module is not None:
            return load_fitz_module()
        return importlib.import_module("fitz")

    def _crop_pdf_region_png(
        pdf_bytes: bytes,
        bbox5: List[float],
        dpi: int,
    ) -> Optional[bytes]:
        if not is_meaningful_bbox(bbox5):
            return None
        try:
            fitz = _load_fitz_module()
        except Exception:
            return None
        try:
            page_no = int(round(float(bbox5[0])))
            if page_no < 1:
                return None
            x, y, w, h = [float(v) for v in bbox5[1:5]]
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                if page_no > doc.page_count:
                    return None
                page = doc.load_page(page_no - 1)
                page_rect = page.rect
                if max(x + w, y + h) <= 1.5:
                    x1 = x * page_rect.width
                    y1 = y * page_rect.height
                    x2 = (x + w) * page_rect.width
                    y2 = (y + h) * page_rect.height
                else:
                    x1 = x
                    y1 = y
                    x2 = x + w
                    y2 = y + h
                rect = fitz.Rect(x1, y1, x2, y2)
                rect = rect.intersect(page_rect)
                if rect.is_empty or rect.width < 2 or rect.height < 2:
                    return None
                zoom = max(1.2, float(dpi) / 72.0)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
                return pix.tobytes("png")
            finally:
                doc.close()
        except Exception:
            return None

    async def _convert_word_to_pdf_with_timeout(
        *,
        file_name: str,
        file_bytes: bytes,
        timeout_sec: float,
    ) -> Tuple[bytes, Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: convert_word_bytes_to_pdf_fn(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    timeout_sec=timeout_sec,
                ),
            ),
            timeout=timeout_sec,
        )

    async def _convert_doc_to_docx_with_timeout(
        *,
        file_name: str,
        file_bytes: bytes,
        timeout_sec: float,
    ) -> Tuple[bytes, Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: convert_doc_bytes_to_docx_fn(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    timeout_sec=timeout_sec,
                ),
            ),
            timeout=timeout_sec,
        )

    return Module2MainDocumentIoBundle(
        crop_pdf_region_png=_crop_pdf_region_png,
        convert_word_to_pdf_with_timeout=_convert_word_to_pdf_with_timeout,
        convert_doc_to_docx_with_timeout=_convert_doc_to_docx_with_timeout,
    )
