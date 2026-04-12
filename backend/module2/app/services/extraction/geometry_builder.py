from __future__ import annotations

"""Geometry helpers for module2 extraction service layer."""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional


@dataclass(frozen=True)
class Module2MainGeometryBundle:
    page_from_bbox: Callable[[List[float]], Optional[int]]
    normalize_bbox: Callable[[Any, Optional[int]], List[float]]
    is_meaningful_bbox: Callable[[List[float]], bool]


def build_module2_main_geometry_bundle() -> Module2MainGeometryBundle:
    def _page_from_bbox(bbox: List[float]) -> Optional[int]:
        if not isinstance(bbox, list) or len(bbox) != 5:
            return None
        try:
            page_no = int(round(float(bbox[0])))
        except (TypeError, ValueError):
            return None
        return page_no if page_no >= 1 else None

    def _normalize_bbox(bbox: Any, page_hint: Optional[int] = None) -> List[float]:
        if not isinstance(bbox, list):
            return []
        if len(bbox) == 5:
            try:
                return [float(x) for x in bbox[:5]]
            except (TypeError, ValueError):
                return []
        if len(bbox) == 4 and page_hint is not None:
            try:
                return [float(page_hint), float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            except (TypeError, ValueError):
                return []
        return []

    def _is_meaningful_bbox(bbox: List[float]) -> bool:
        if len(bbox) != 5:
            return False
        try:
            _, x, y, w, h = [float(v) for v in bbox[:5]]
        except Exception:
            return False
        if w <= 0 or h <= 0:
            return False
        if x <= 0.0001 and y <= 0.0001 and w >= 0.995 and h >= 0.995:
            return False
        return True

    return Module2MainGeometryBundle(
        page_from_bbox=_page_from_bbox,
        normalize_bbox=_normalize_bbox,
        is_meaningful_bbox=_is_meaningful_bbox,
    )
