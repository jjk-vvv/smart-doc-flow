from __future__ import annotations

import base64
import json
import urllib.request
from typing import Any, Callable, Dict, Optional


ResolveText = Callable[[], str]
ResolveUrl = Callable[[str], str]
BuildHeaders = Callable[[str, str], Dict[str, str]]
ExtractJsonObject = Callable[[str], Optional[Dict[str, Any]]]
ExtractCandidateText = Callable[[str], str]


class VisionRequestRuntime:
    """Render page PNGs and execute Gemini vision requests with injected helpers."""

    def __init__(
        self,
        *,
        gemini_vision_dpi: int,
        gemini_vision_max_side_px: int,
        gemini_vision_model: str,
        gemini_vision_timeout_sec: float,
        gemini_vision_max_output_tokens: int,
        gemini_native_fallback_enabled: bool,
        resolve_api_key: ResolveText,
        resolve_native_api_key: ResolveText,
        resolve_native_url: ResolveUrl,
        build_google_native_url: ResolveUrl,
        build_headers: BuildHeaders,
        extract_json_object: ExtractJsonObject,
        extract_candidate_text: ExtractCandidateText,
        request_factory: Callable[..., Any] = urllib.request.Request,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.gemini_vision_dpi = max(96, int(gemini_vision_dpi or 96))
        self.gemini_vision_max_side_px = max(768, int(gemini_vision_max_side_px or 768))
        self.gemini_vision_model = str(gemini_vision_model or "").strip()
        self.gemini_vision_timeout_sec = max(1.0, float(gemini_vision_timeout_sec or 1.0))
        self.gemini_vision_max_output_tokens = max(1, int(gemini_vision_max_output_tokens or 1))
        self.gemini_native_fallback_enabled = bool(gemini_native_fallback_enabled)
        self._resolve_api_key = resolve_api_key
        self._resolve_native_api_key = resolve_native_api_key
        self._resolve_native_url = resolve_native_url
        self._build_google_native_url = build_google_native_url
        self._build_headers = build_headers
        self._extract_json_object = extract_json_object
        self._extract_candidate_text = extract_candidate_text
        self._request_factory = request_factory
        self._urlopen = urlopen

    def render_page_png_for_vision(self, page: Any) -> bytes:
        try:
            import fitz  # pymupdf
        except Exception:
            return b""

        scale = self.gemini_vision_dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        max_side = max(pix.width, pix.height)
        if max_side > self.gemini_vision_max_side_px:
            shrink = self.gemini_vision_max_side_px / float(max_side)
            matrix = fitz.Matrix(scale * shrink, scale * shrink)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
        try:
            return pix.tobytes("png")
        except Exception:
            return b""

    def extract_payload(self, image_png: bytes, focus: str = "mixed") -> Optional[Dict[str, Any]]:
        text = self.generate(image_png, focus=focus)
        if not text:
            return None
        return self._extract_json_object(text)

    def generate(self, image_png: bytes, focus: str = "mixed") -> str:
        api_key = self._resolve_api_key()
        native_api_key = self._resolve_native_api_key()
        if not api_key and not native_api_key:
            return ""

        focus_key = str(focus or "mixed").strip().lower()
        if focus_key not in {"mixed", "table", "figure"}:
            focus_key = "mixed"

        prompt = self._build_prompt(focus_key)
        model = self.gemini_vision_model or "gemini-3.1-pro-preview"
        request_candidates: list[tuple[str, str]] = []
        primary_url = self._resolve_native_url(model)
        if primary_url and api_key:
            request_candidates.append((primary_url, api_key))
        if self.gemini_native_fallback_enabled and native_api_key:
            google_url = self._build_google_native_url(model)
            if google_url and all(url != google_url or key != native_api_key for url, key in request_candidates):
                request_candidates.append((google_url, native_api_key))
        if not request_candidates:
            return ""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64.b64encode(image_png).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": self.gemini_vision_max_output_tokens,
            },
        }

        raw = ""
        for url, auth_key in request_candidates:
            try:
                request = self._request_factory(
                    url=url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers=self._build_headers(url, auth_key),
                    method="POST",
                )
                with self._urlopen(request, timeout=self.gemini_vision_timeout_sec) as response:
                    raw = response.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
            if raw:
                break
        if not raw:
            return ""
        return self._extract_candidate_text(raw)

    @staticmethod
    def _build_prompt(focus_key: str) -> str:
        if focus_key == "figure":
            return (
                "Extract visible figure and chart information from this page image. "
                "Return strict JSON only, with no markdown fences. "
                "Return at most 4 figures. Do not return tables. "
                "Use this exact schema: "
                "{\"tables\":[],"
                "\"figures\":[{"
                "\"title\":\"\","
                "\"type\":\"chart|diagram|photo|other\","
                "\"caption\":\"\","
                "\"content_modes\":[\"dataframe|topology|text|visual\"],"
                "\"key_points\":[\"...\"],"
                "\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],"
                "\"axes\":{\"x\":\"\",\"y\":\"\"},"
                "\"legend\":[\"...\"],"
                "\"text_blocks\":[\"...\"],"
                "\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"],...]},"
                "\"topology\":{\"nodes\":[{\"id\":\"\",\"label\":\"\",\"type\":\"\"}],\"edges\":[{\"source\":\"\",\"target\":\"\",\"label\":\"\"}]},"
                "\"confidence\":0.0"
                "}],"
                "\"insights\":[\"...\"]}. "
                "Keep output compact, but for charts and diagrams you should recover the fullest visible structured data you can. "
                "Preserve row order, series order, and axis order. Do not arbitrarily truncate visible dataframe headers or rows. "
                "If exact numeric values are visible, prefer dataframe and key_values over long prose. "
                "Do not invent values that are not visible."
            )
        if focus_key == "table":
            return (
                "Extract visible table information from this page image. "
                "Return strict JSON only, with no markdown fences. "
                "Return at most 3 tables. Do not return figures. "
                "Use this exact schema: "
                "{\"tables\":[{"
                "\"title\":\"\","
                "\"caption\":\"\","
                "\"headers\":[\"...\"],"
                "\"rows\":[[\"...\"],...],"
                "\"notes\":[\"...\"],"
                "\"confidence\":0.0"
                "}],"
                "\"figures\":[],"
                "\"insights\":[\"...\"]}. "
                "Keep output compact. For each table, keep at most 8 rows and 8 columns. "
                "Do not invent values that are not visible."
            )
        return (
            "Extract visible structured information from this page image. "
            "Return strict JSON only, with no markdown fences. "
            "Use this exact schema: "
            "{\"tables\":[{\"title\":\"\",\"caption\":\"\",\"headers\":[\"...\"],\"rows\":[[\"...\"],...],\"notes\":[\"...\"],\"confidence\":0.0}],"
            "\"figures\":[{\"title\":\"\",\"type\":\"chart|diagram|photo|other\",\"caption\":\"\",\"content_modes\":[\"dataframe|topology|text|visual\"],"
            "\"key_points\":[\"...\"],\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],\"axes\":{\"x\":\"\",\"y\":\"\"},"
            "\"legend\":[\"...\"],\"text_blocks\":[\"...\"],\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"],...]},"
            "\"topology\":{\"nodes\":[{\"id\":\"\",\"label\":\"\",\"type\":\"\"}],\"edges\":[{\"source\":\"\",\"target\":\"\",\"label\":\"\"}]},\"confidence\":0.0}],"
            "\"insights\":[\"...\"]}. "
            "Keep output compact. Return at most 2 tables and 3 figures. "
            "For charts and diagrams, recover the fullest visible dataframe you can without inventing hidden values. "
            "Do not arbitrarily truncate visible headers, rows, or series labels. "
            "Do not invent values that are not visible."
        )
