from __future__ import annotations

import re
from typing import Any, Callable, Dict, List


NormalizeText = Callable[[str], str]


class PdfVisualProfileRuntime:
    """Classify PDF visual profiles and MinerU fallback strategy."""

    def __init__(
        self,
        *,
        native_text_threshold: int,
        visual_probe_pages: int,
        mineru_method: str,
        mineru_scanned_method: str,
        mineru_method_fallbacks: str,
        visual_first_max_pages_scanned: int,
        mineru_text_first_office_pdf_enable: bool,
        mineru_text_first_office_pdf_min_pages: int,
        mineru_text_first_office_pdf_min_probe_chars: int,
        pdf_text_first_enable: bool,
        pdf_text_heavy_min_probe_chars: int,
        pdf_text_heavy_min_chars_per_page: int,
        pdf_text_heavy_max_visual_cues: int,
        pdf_mixed_text_pref_min_chars_per_page: int,
        pdf_mixed_text_pref_max_visual_cues: int,
        pdf_text_only_short_circuit_enable: bool,
        normalize_text: NormalizeText,
    ) -> None:
        self.native_text_threshold = int(native_text_threshold or 0)
        self.visual_probe_pages = int(visual_probe_pages or 0)
        self.mineru_method = str(mineru_method or "")
        self.mineru_scanned_method = str(mineru_scanned_method or "")
        self.mineru_method_fallbacks = str(mineru_method_fallbacks or "")
        self.visual_first_max_pages_scanned = int(visual_first_max_pages_scanned or 0)
        self.mineru_text_first_office_pdf_enable = bool(mineru_text_first_office_pdf_enable)
        self.mineru_text_first_office_pdf_min_pages = int(mineru_text_first_office_pdf_min_pages or 0)
        self.mineru_text_first_office_pdf_min_probe_chars = int(mineru_text_first_office_pdf_min_probe_chars or 0)
        self.pdf_text_first_enable = bool(pdf_text_first_enable)
        self.pdf_text_heavy_min_probe_chars = int(pdf_text_heavy_min_probe_chars or 0)
        self.pdf_text_heavy_min_chars_per_page = int(pdf_text_heavy_min_chars_per_page or 0)
        self.pdf_text_heavy_max_visual_cues = int(pdf_text_heavy_max_visual_cues or 0)
        self.pdf_mixed_text_pref_min_chars_per_page = int(pdf_mixed_text_pref_min_chars_per_page or 0)
        self.pdf_mixed_text_pref_max_visual_cues = int(pdf_mixed_text_pref_max_visual_cues or 0)
        self.pdf_text_only_short_circuit_enable = bool(pdf_text_only_short_circuit_enable)
        self._normalize_text = normalize_text

    def summarize_pdf_metadata_signals(self, reader: Any) -> Dict[str, Any]:
        metadata = getattr(reader, "metadata", None) or {}
        creator = self._normalize_text(str(metadata.get("/Creator") or ""))
        producer = self._normalize_text(str(metadata.get("/Producer") or ""))
        haystack = f"{creator}\n{producer}".strip().lower()
        haystack_normalized = re.sub(r"[^a-z0-9]+", " ", haystack).strip()
        office_keywords = (
            "microsoft word",
            "microsoft office",
            "libreoffice",
            "openoffice",
            "wps office",
            "wps writer",
        )
        office_like = any(keyword in haystack_normalized for keyword in office_keywords)
        return {
            "creator": creator,
            "producer": producer,
            "normalized": haystack_normalized,
            "office_like": office_like,
        }

    def count_pdf_visual_cues(self, text: str) -> int:
        normalized = self._normalize_text(text)
        if not normalized:
            return 0
        patterns = (
            r"\bfig(?:ure)?\.?\s*[A-Za-z0-9]",
            r"\btable\s*[A-Za-z0-9]",
            r"\bchart\b",
            r"\bdiagram\b",
            r"\bequation\b",
            r"\beq\.\s*[A-Za-z0-9]",
            r"\bformula\b",
            r"图\s*[0-9A-Za-z一二三四五六七八九十百千]",
            r"表\s*[0-9A-Za-z一二三四五六七八九十百千]",
            r"(公式|方程|流程图|示意图|曲线|柱状|折线|饼图|反应式|化学式)",
        )
        hit_count = 0
        for pattern in patterns:
            hit_count += len(re.findall(pattern, normalized, flags=re.IGNORECASE))
        return min(24, int(hit_count))

    def ordered_mineru_fallbacks(self, requested_method: str) -> List[str]:
        requested = str(requested_method or "").strip().lower()
        raw_methods = [requested]
        raw_methods.extend(
            [part.strip().lower() for part in str(self.mineru_method_fallbacks or "").split(",") if part.strip()]
        )
        ordered: List[str] = []
        seen = set()
        for item in raw_methods:
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return [item for item in ordered if item != requested]

    def classify_pdf_visual_profile(
        self,
        *,
        file_name: str,
        page_count: int,
        probe_pages: int,
        probe_chars: int,
        probe_text: str,
        pdf_metadata_signals: Dict[str, Any],
    ) -> Dict[str, Any]:
        effective_probe_pages = max(1, int(probe_pages or 1))
        chars_per_page = float(probe_chars) / float(effective_probe_pages)
        office_like = bool(pdf_metadata_signals.get("office_like"))
        visual_cue_hits = self.count_pdf_visual_cues(f"{file_name}\n{probe_text}")
        method_default = str(self.mineru_method or "auto").strip().lower() or "auto"
        scanned_method_raw = str(self.mineru_scanned_method or self.mineru_method or "auto").strip().lower() or "auto"
        scanned_method = "ocr" if scanned_method_raw == "auto" else scanned_method_raw
        scanned_fallbacks = ["txt"] if scanned_method == "ocr" else self.ordered_mineru_fallbacks(scanned_method)

        if probe_chars < self.native_text_threshold:
            method = scanned_method
            return {
                "profile": "visual_scanned_pdf",
                "reason": "low_native_text",
                "method": method,
                "method_fallbacks": scanned_fallbacks,
                "stop_on_usable_text": False,
                "page_count_cap": self.visual_first_max_pages_scanned,
                "probe_chars_per_page": round(chars_per_page, 2),
                "visual_cue_hits": int(visual_cue_hits),
                "office_like": office_like,
            }

        if (
            self.mineru_text_first_office_pdf_enable
            and method_default == "auto"
            and office_like
            and page_count >= self.mineru_text_first_office_pdf_min_pages
            and probe_chars >= self.mineru_text_first_office_pdf_min_probe_chars
        ):
            method = "txt"
            return {
                "profile": "office_text_pdf",
                "reason": "office_pdf_strong_native_text",
                "method": method,
                "method_fallbacks": self.ordered_mineru_fallbacks(method),
                "stop_on_usable_text": False,
                "page_count_cap": page_count,
                "probe_chars_per_page": round(chars_per_page, 2),
                "visual_cue_hits": int(visual_cue_hits),
                "office_like": office_like,
            }

        short_pdf = page_count <= max(self.visual_probe_pages, 12)
        if (
            self.pdf_text_first_enable
            and probe_chars >= self.pdf_text_heavy_min_probe_chars
            and chars_per_page >= float(self.pdf_text_heavy_min_chars_per_page)
            and visual_cue_hits <= self.pdf_text_heavy_max_visual_cues
            and short_pdf
        ):
            method = "txt"
            return {
                "profile": "text_heavy_pdf",
                "reason": "strong_native_text_low_visual_cues",
                "method": method,
                "method_fallbacks": self.ordered_mineru_fallbacks(method),
                "stop_on_usable_text": bool(self.pdf_text_only_short_circuit_enable),
                "page_count_cap": page_count,
                "probe_chars_per_page": round(chars_per_page, 2),
                "visual_cue_hits": int(visual_cue_hits),
                "office_like": office_like,
            }

        if (
            self.pdf_text_first_enable
            and chars_per_page >= float(self.pdf_mixed_text_pref_min_chars_per_page)
            and visual_cue_hits <= self.pdf_mixed_text_pref_max_visual_cues
        ):
            method = "txt"
            tiny_low_cue_pdf = page_count <= 2 and visual_cue_hits <= 0
            return {
                "profile": "mixed_text_pref_pdf",
                "reason": (
                    "strong_native_text_prefers_txt_no_visual_cues"
                    if tiny_low_cue_pdf
                    else "strong_native_text_prefers_txt"
                ),
                "method": method,
                "method_fallbacks": self.ordered_mineru_fallbacks(method),
                "stop_on_usable_text": bool(self.pdf_text_only_short_circuit_enable and tiny_low_cue_pdf),
                "page_count_cap": page_count,
                "probe_chars_per_page": round(chars_per_page, 2),
                "visual_cue_hits": int(visual_cue_hits),
                "office_like": office_like,
            }

        return {
            "profile": "mixed_visual_pdf",
            "reason": "configured_default",
            "method": method_default,
            "method_fallbacks": self.ordered_mineru_fallbacks(method_default),
            "stop_on_usable_text": False,
            "page_count_cap": page_count,
            "probe_chars_per_page": round(chars_per_page, 2),
            "visual_cue_hits": int(visual_cue_hits),
            "office_like": office_like,
        }
