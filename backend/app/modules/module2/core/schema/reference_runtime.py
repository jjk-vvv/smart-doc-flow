from __future__ import annotations

from html import escape
from typing import Dict, List


class ReferenceRuntime:
    """Manage ref-tag emission and bbox map registration for extracted artifacts."""

    @staticmethod
    def append_ref(
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        ref_id: str,
        text: str,
        bbox: List[float],
    ) -> None:
        if not ref_id or ref_id in bbox_map:
            return
        parts.append(f'<ref id="{ref_id}">{escape(str(text or ""))}</ref>')
        bbox_map[ref_id] = [float(x) for x in bbox[:5]]
