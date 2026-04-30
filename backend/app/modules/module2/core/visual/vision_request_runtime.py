from __future__ import annotations

import base64
import json
import urllib.request
from typing import Any, Callable, Dict, Optional

from app.core.ai_api_logging import (
    log_ai_api_exception,
    log_ai_api_request,
    log_ai_api_response,
)


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
        gemini_vision_base_url: str,
        gemini_vision_endpoint_style: str,
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
        self.gemini_vision_base_url = str(gemini_vision_base_url or "").strip()
        self.gemini_vision_endpoint_style = self._normalize_endpoint_style(gemini_vision_endpoint_style)
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
        model = self.gemini_vision_model or "qwen3-vl-plus"
        if self.gemini_vision_endpoint_style == "openai_chat_completions":
            return self._generate_openai_chat(
                image_png=image_png,
                prompt=prompt,
                model=model,
                api_key=api_key,
            )

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
                log_ai_api_request(
                    api_url=url,
                    request_body=payload,
                    model=model,
                    logger_name="app.modules.module2.vision.runtime.ai_api",
                    config_prefix="MODULE2",
                )
                request = self._request_factory(
                    url=url,
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers=self._build_headers(url, auth_key),
                    method="POST",
                )
                with self._urlopen(request, timeout=self.gemini_vision_timeout_sec) as response:
                    raw = response.read().decode("utf-8", errors="ignore")
                log_ai_api_response(
                    response_text=raw,
                    logger_name="app.modules.module2.vision.runtime.ai_api",
                    config_prefix="MODULE2",
                )
            except Exception as exc:
                log_ai_api_exception(
                    exc=exc,
                    logger_name="app.modules.module2.vision.runtime.ai_api",
                    config_prefix="MODULE2",
                )
                continue
            if raw:
                break
        if not raw:
            return ""
        return self._extract_candidate_text(raw)

    def _generate_openai_chat(self, *, image_png: bytes, prompt: str, model: str, api_key: str) -> str:
        url = self._resolve_openai_chat_url()
        if not url or not api_key:
            return ""
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64.b64encode(image_png).decode('ascii')}",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": self.gemini_vision_max_output_tokens,
            "stream": False,
        }
        try:
            log_ai_api_request(
                api_url=url,
                request_body=payload,
                model=model,
                logger_name="app.modules.module2.vision.runtime.ai_api",
                config_prefix="MODULE2",
            )
            request = self._request_factory(
                url=url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "smart-doc-flow-module2-parser/1.0",
                },
                method="POST",
            )
            with self._urlopen(request, timeout=self.gemini_vision_timeout_sec) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            log_ai_api_response(
                response_text=raw,
                logger_name="app.modules.module2.vision.runtime.ai_api",
                config_prefix="MODULE2",
            )
        except Exception as exc:
            log_ai_api_exception(
                exc=exc,
                logger_name="app.modules.module2.vision.runtime.ai_api",
                config_prefix="MODULE2",
            )
            return ""
        return self._extract_openai_choice_text(raw)

    def _resolve_openai_chat_url(self) -> str:
        raw = str(self.gemini_vision_base_url or "").strip().rstrip("/")
        if not raw:
            return ""
        for suffix in ("/v1/chat/completions", "/chat/completions"):
            if raw.endswith(suffix):
                return raw
        for suffix in ("/v1/responses", "/responses"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)].rstrip("/")
                break
        if raw.endswith("/v1"):
            return f"{raw}/chat/completions"
        return f"{raw}/v1/chat/completions"

    @classmethod
    def _extract_openai_choice_text(cls, raw: str) -> str:
        if not raw:
            return ""
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        choices = obj.get("choices") if isinstance(obj.get("choices"), list) else []
        texts: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            text = cls._coerce_openai_content(message.get("content"))
            if text.strip():
                texts.append(text.strip())
        return "\n".join(texts).strip()

    @staticmethod
    def _coerce_openai_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces: list[str] = []
            for item in content:
                if isinstance(item, str):
                    pieces.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    pieces.append(text)
                    continue
                if isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        pieces.append(value)
            return "".join(pieces)
        return ""

    @staticmethod
    def _normalize_endpoint_style(raw_style: str) -> str:
        raw = str(raw_style or "").strip().lower()
        if raw in {"openai", "openai_chat", "chat_completions", "openai_chat_completions"}:
            return "openai_chat_completions"
        if raw in {"native", "google_native", "gemini_native"}:
            raise RuntimeError(
                "Native Gemini/Google vision endpoint style is disabled; use openai_chat_completions."
            )
        return "openai_chat_completions"

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
