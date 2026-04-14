from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Tuple


class RoiCropper:
    """Load MinerU ROI images or crop fallback regions from PDF pages."""

    def __init__(
        self,
        *,
        table_dpi: int = 260,
        figure_dpi: int = 220,
        expand_ratio: float = 0.03,
        max_side_px: int = 2800,
    ) -> None:
        self.table_dpi = max(120, int(table_dpi))
        self.figure_dpi = max(120, int(figure_dpi))
        self.expand_ratio = max(0.0, min(0.2, float(expand_ratio)))
        self.max_side_px = max(1200, int(max_side_px))

    def load_or_crop(
        self,
        *,
        item: Dict[str, Any],
        pdf_bytes: bytes,
        is_table: bool,
    ) -> Tuple[bytes, str, str]:
        img_path = str(item.get("img_path", "") or "").strip()
        if img_path:
            p = Path(img_path)
            if p.exists() and p.is_file():
                data = p.read_bytes()
                if data:
                    mime, _ = mimetypes.guess_type(p.name)
                    return data, (mime or "image/jpeg"), "mineru_img_path"

        cropped = self._crop_from_pdf(item=item, pdf_bytes=pdf_bytes, is_table=is_table)
        if cropped[0]:
            return cropped
        return b"", "", ""

    def _crop_from_pdf(
        self,
        *,
        item: Dict[str, Any],
        pdf_bytes: bytes,
        is_table: bool,
    ) -> Tuple[bytes, str, str]:
        try:
            import fitz  # pymupdf
        except Exception:
            return b"", "", ""
        if not pdf_bytes:
            return b"", "", ""

        page_no = self._to_int(item.get("page"), default=1)
        bbox = self._safe_bbox(item.get("bbox"))
        if page_no <= 0:
            return b"", "", ""

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            return b"", "", ""
        try:
            page_idx = page_no - 1
            if page_idx < 0 or page_idx >= len(doc):
                return b"", "", ""
            page = doc.load_page(page_idx)
            rect = page.rect
            x1, y1, x2, y2 = self._bbox_to_page_points(
                bbox=bbox,
                page_width=max(float(rect.width), 1.0),
                page_height=max(float(rect.height), 1.0),
            )
            if x2 <= x1 or y2 <= y1:
                return b"", "", ""

            pad_x = (x2 - x1) * self.expand_ratio
            pad_y = (y2 - y1) * self.expand_ratio
            clip = fitz.Rect(
                max(0.0, x1 - pad_x),
                max(0.0, y1 - pad_y),
                min(float(rect.width), x2 + pad_x),
                min(float(rect.height), y2 + pad_y),
            )
            if clip.width <= 1 or clip.height <= 1:
                return b"", "", ""

            dpi = self.table_dpi if is_table else self.figure_dpi
            scale = dpi / 72.0
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            max_side = max(pix.width, pix.height)
            if max_side > self.max_side_px:
                shrink = self.max_side_px / float(max_side)
                matrix = fitz.Matrix(scale * shrink, scale * shrink)
                pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            try:
                return pix.tobytes("png"), "image/png", "pdf_crop"
            except Exception:
                return b"", "", ""
        finally:
            doc.close()

    @staticmethod
    def _bbox_to_page_points(
        *,
        bbox: List[float],
        page_width: float,
        page_height: float,
    ) -> Tuple[float, float, float, float]:
        x1, y1, x2, y2 = bbox
        # Normalized box [0,1]
        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
            x1 *= page_width
            x2 *= page_width
            y1 *= page_height
            y2 *= page_height
        else:
            # If layout coordinates are in another page raster scale, rescale.
            sx = 1.0
            sy = 1.0
            if x2 > page_width * 1.2 and x2 > 1:
                sx = page_width / float(x2)
            if y2 > page_height * 1.2 and y2 > 1:
                sy = page_height / float(y2)
            x1 *= sx
            x2 *= sx
            y1 *= sy
            y2 *= sy

        x1 = max(0.0, min(page_width, float(x1)))
        y1 = max(0.0, min(page_height, float(y1)))
        x2 = max(0.0, min(page_width, float(x2)))
        y2 = max(0.0, min(page_height, float(y2)))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        return x1, y1, x2, y2

    @staticmethod
    def _safe_bbox(raw_bbox: Any) -> List[float]:
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return [0.0, 0.0, 1.0, 1.0]
        out: List[float] = []
        for i in range(4):
            try:
                out.append(float(raw_bbox[i]))
            except (TypeError, ValueError):
                out.append(0.0 if i < 2 else 1.0)
        x1, y1, x2, y2 = out
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        return [x1, y1, x2, y2]

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
