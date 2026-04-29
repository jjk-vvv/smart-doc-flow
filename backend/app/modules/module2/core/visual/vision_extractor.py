from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import requests
from requests.exceptions import HTTPError, RequestException

from ...integrations.llm.provider import resolve_llm_native_api_url
from ..integration.gemini_native_transport_runtime import GeminiNativeTransportRuntime


class GeminiVisionExtractor:
    """Gemini Vision JSON extractor with prompt layering and disk cache."""

    def __init__(
        self,
        *,
        api_key: str,
        native_api_key: str = "",
        model: str = "qwen3-vl-plus",
        base_url: str = "",
        endpoint_style: str = "openai_chat_completions",
        timeout_sec: float = 25.0,
        max_output_tokens: int = 4096,
        retry_count: int = 1,
        cache_dir: str | None = None,
        enable_cache: bool = True,
        reasoning_effort: str = "minimal",
        native_fallback_enabled: bool = False,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.native_api_key = (native_api_key or "").strip()
        self.model = (model or "qwen3-vl-plus").strip() or "qwen3-vl-plus"
        self.base_url = (base_url or "").strip()
        self.endpoint_style = self._normalize_endpoint_style(endpoint_style)
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.max_output_tokens = max(512, int(max_output_tokens))
        self.retry_count = max(0, int(retry_count))
        self.request_retry_attempts = max(
            self.retry_count + 1,
            int(os.getenv("MODULE2_VISION_PROVIDER_RETRY_ATTEMPTS", "4")),
        )
        self.request_retry_backoff_sec = max(
            0.2,
            float(os.getenv("MODULE2_VISION_PROVIDER_RETRY_BACKOFF_SEC", "1.2")),
        )
        self.enable_cache = bool(enable_cache)
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        effort = str(reasoning_effort or "minimal").strip().lower()
        self.reasoning_effort = effort if effort in {"minimal", "low", "medium", "high"} else "minimal"
        self.native_fallback_enabled = bool(native_fallback_enabled)
        self.prompt_version = f"v7_visual_full_chart_json_{self.endpoint_style}"
        self._native_transport_runtime = GeminiNativeTransportRuntime(
            resolve_native_api_url=resolve_llm_native_api_url,
            user_agent="smart-doc-flow-module2-vision/1.0",
            default_model="gemini-2.5-flash",
            connection_close=True,
        )
        self._state_lock = Lock()
        self._last_debug: Dict[str, Any] = {}
        self.reset_stats()

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.endpoint_style == "openai_chat_completions")

    def reset_stats(self) -> None:
        with self._state_lock:
            self._stats = {
                "requests": 0,
                "cache_hits": 0,
                "provider_success": 0,
                "provider_failures": 0,
                "transport_failures": 0,
                "retryable_transport_failures": 0,
                "request_retries": 0,
                "http_errors": 0,
                "parse_success": 0,
                "parse_failures": 0,
                "truncated_responses": 0,
            }
            self._last_debug = {}

    def get_stats_snapshot(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(self._stats)

    def get_last_debug(self) -> Dict[str, Any]:
        with self._state_lock:
            return dict(self._last_debug)

    def _bump_stat(self, key: str, amount: int = 1) -> None:
        with self._state_lock:
            self._stats[key] = int(self._stats.get(key, 0) or 0) + int(amount)

    def _set_debug(self, **kwargs: Any) -> None:
        cleaned: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            if isinstance(value, str):
                cleaned[key] = value[:1800]
            else:
                cleaned[key] = value
        with self._state_lock:
            self._last_debug = cleaned

    def extract_table(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.ready or not image_bytes:
            return None
        context_json = self._compact_json(context, max_chars=2200)
        prompt = (
            "Extract one visible table from this cropped PDF ROI image.\n"
            "Return strict JSON only. No markdown. Use this exact schema:\n"
            "{"
            "\"table\":{"
            "\"title\":\"\","
            "\"caption\":\"\","
            "\"header_rows\":[[\"...\"]],"
            "\"headers\":[\"...\"],"
            "\"rows\":[[\"...\"]],"
            "\"units\":{},"
            "\"notes\":[\"...\"],"
            "\"confidence\":0.0"
            "}"
            "}\n"
            "Use only visible content. Preserve row and column order. Keep blanks as empty strings. "
            "If the table is unreadable, keep arrays empty and confidence 0.0.\n"
            f"Context:\n{context_json}"
        )
        payload = self._generate_json(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            mode="table",
            context=context,
        )
        if not isinstance(payload, dict):
            return None
        table_obj = payload.get("table")
        if isinstance(table_obj, dict):
            return table_obj
        # Compatibility fallback if model returns flat shape.
        if any(k in payload for k in ("headers", "rows", "header_rows")):
            return payload
        return None

    def extract_figure(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        context: Dict[str, Any],
        allow_refine: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not self.ready or not image_bytes:
            return None
        context_json = self._compact_json(context, max_chars=2000)
        prompt = (
            "Analyze one cropped image-like ROI from a PDF. The ROI may be a chart, diagram, table-like image, formula/equation snapshot, photo, or generic figure.\n"
            "Return strict JSON only. No markdown. Use this exact schema:\n"
            "{"
            "\"figure\":{"
            "\"title\":\"\","
            "\"caption\":\"\","
            "\"type\":\"chart|diagram|formula|photo|other\","
            "\"content_modes\":[\"dataframe|topology|text|visual\"],"
            "\"axes\":{\"x\":\"\",\"y\":\"\"},"
            "\"legend\":[\"...\"],"
            "\"insights\":[\"...\"],"
            "\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],"
            "\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"]]},"
            "\"topology\":{\"nodes\":[{\"id\":\"\",\"label\":\"\",\"type\":\"\"}],\"edges\":[{\"source\":\"\",\"target\":\"\",\"label\":\"\"}]},"
            "\"text_blocks\":[\"...\"],"
            "\"confidence\":0.0"
            "}"
            "}\n"
            "Use only visible evidence. Keep text concise, but if this ROI is a chart or data graphic, recover the fullest visible dataframe you can.\n"
            "If the ROI is mainly a formula or equation image, preserve the visible symbolic text exactly in text_blocks and insights.\n"
            "Preserve visible series order, legend labels, axis labels, and row order. Do not collapse readable numeric points into prose.\n"
            "Do not arbitrarily drop later rows or headers if they are visible.\n"
            f"Context:\n{context_json}"
        )
        payload = self._generate_json(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            mode="figure",
            context=context,
        )
        if not isinstance(payload, dict):
            return None
        figure_obj = payload.get("figure")
        if isinstance(figure_obj, dict):
            if self._should_refine_chart_extraction(figure_obj, context, allow_refine=allow_refine):
                refined = self._refine_chart_figure(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    context=context,
                    primary=figure_obj,
                )
                if isinstance(refined, dict):
                    figure_obj = self._merge_figure_payload(figure_obj, refined)
            return figure_obj
        if any(k in payload for k in ("caption", "type", "insights")):
            return payload
        return None

    def _refine_chart_figure(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        context: Dict[str, Any],
        primary: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        refine_context = dict(context or {})
        refine_context["primary_figure"] = {
            "title": str(primary.get("title", "") or ""),
            "caption": str(primary.get("caption", "") or ""),
            "type": str(primary.get("type", "") or ""),
            "insights": primary.get("insights") if isinstance(primary.get("insights"), list) else [],
        }
        context_json = self._compact_json(refine_context, max_chars=2200)
        prompt = (
            "Recover a best-effort dataframe from this single chart ROI image.\n"
            "Return strict JSON only. No markdown. Use only visible values. "
            "Prefer grounded dataframe rows over prose. Recover as many visible rows, headers, series labels, and units as possible. "
            "If exact values are unreadable, keep the dataframe empty.\n"
            "Use this exact schema:\n"
            "{"
            "\"figure\":{"
            "\"title\":\"\","
            "\"caption\":\"\","
            "\"type\":\"chart|diagram|photo|other\","
            "\"content_modes\":[\"dataframe|text|visual\"],"
            "\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],"
            "\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"]]},"
            "\"text_blocks\":[\"...\"],"
            "\"insights\":[\"...\"],"
            "\"confidence\":0.0"
            "}"
            "}\n"
            f"Context:\n{context_json}"
        )
        payload = self._generate_json(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            mode="figure_chart_refine",
            context=refine_context,
        )
        if not isinstance(payload, dict):
            return None
        figure_obj = payload.get("figure")
        if isinstance(figure_obj, dict):
            return figure_obj
        if any(k in payload for k in ("caption", "type", "insights", "dataframe", "key_values")):
            return payload
        return None

    def _generate_json(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
        mode: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        self._bump_stat("requests")
        cache_key = self._build_cache_key(
            mode=mode,
            prompt=prompt,
            image_bytes=image_bytes,
            context=context,
        )
        if self.enable_cache and self.cache_dir is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                self._bump_stat("cache_hits")
                self._set_debug(
                    mode=mode,
                    status="cache_hit",
                    request_source="cache",
                    cache_key=cache_key,
                )
                return cached

        raw_content = ""
        finish_reason = ""
        model_name = self.model
        request_source = ""
        last_exc_text = ""
        try:
            response = self._request_native_multimodal(
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
            raw_content = str(response.get("content", "") or "").strip()
            finish_reason = str(response.get("finish_reason", "") or "").strip()
            model_name = str(response.get("model", "") or self.model)
            request_source = str(response.get("request_source", "") or "openai_chat_completions")
        except Exception as exc:
            last_exc_text = f"{type(exc).__name__}: {exc}"

        if raw_content:
            self._bump_stat("provider_success")
            if finish_reason.lower() == "length":
                self._bump_stat("truncated_responses")
            payload_value = self._extract_json_payload(raw_content)
            payload = self._normalize_payload_shape(payload_value, mode=mode)
            if payload is not None:
                self._bump_stat("parse_success")
                self._set_debug(
                    mode=mode,
                    status="ok",
                    request_source=request_source or "openai_chat_completions",
                    finish_reason=finish_reason,
                    model=model_name,
                    parse_mode=self._infer_parse_mode(payload_value),
                    raw_excerpt=raw_content[:1200],
                )
                if self.enable_cache and self.cache_dir is not None:
                    self._cache_put(cache_key, payload)
                return payload
            self._bump_stat("parse_failures")
            self._set_debug(
                mode=mode,
                status="parse_failed",
                request_source=request_source or "openai_chat_completions",
                finish_reason=finish_reason,
                model=model_name,
                parse_mode="unrecognized",
                raw_excerpt=raw_content[:1200],
                error="vision_response_unrecognized",
            )
            return None

        self._bump_stat("provider_failures")
        lowered_error = last_exc_text.lower()
        if "http error" in lowered_error or "401" in last_exc_text or "403" in last_exc_text or "429" in last_exc_text:
            self._bump_stat("http_errors")
        if last_exc_text:
            self._bump_stat("transport_failures")
            if self._is_retryable_request_error_text(last_exc_text):
                self._bump_stat("retryable_transport_failures")
        self._set_debug(
            mode=mode,
            status="request_failed",
            request_source=request_source or "openai_chat_completions",
            error=(last_exc_text or "no_usable_vision_provider")[:1200],
        )
        return None

    def _request_native_multimodal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> Dict[str, str]:
        if self.endpoint_style == "openai_chat_completions":
            return self._request_openai_multimodal(
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
        raise RuntimeError("Native Gemini/Google vision endpoints are disabled; use openai_chat_completions.")

        last_exc: Optional[Exception] = None
        request_candidates: list[tuple[str, str, str]] = []
        primary_url = self._resolve_primary_native_url()
        primary_key = self._resolve_primary_api_key()
        if primary_url and primary_key:
            request_candidates.append((primary_url, primary_key, "gemini_native"))
        if self._allow_google_native_fallback():
            google_key = self.native_api_key.strip()
            google_url = self._native_transport_runtime.build_google_native_url(self.model)
            if google_key and google_url and all(url != google_url or key != google_key for url, key, _ in request_candidates):
                request_candidates.append((google_url, google_key, "gemini_native_google_fallback"))
        if not request_candidates:
            raise RuntimeError("no_usable_vision_provider")

        for url, api_key, source in request_candidates:
            for attempt in range(1, self.request_retry_attempts + 1):
                try:
                    return self._post_native_multimodal(
                        url=url,
                        api_key=api_key,
                        source=source,
                        prompt=prompt,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                    )
                except Exception as exc:
                    last_exc = exc
                    if not self._should_retry_transport_exception(exc) or attempt >= self.request_retry_attempts:
                        break
                    self._bump_stat("request_retries")
                    time.sleep(self._retry_sleep_seconds(attempt))
        raise last_exc or RuntimeError("vision provider returned empty response")

    def _post_native_multimodal(
        self,
        *,
        url: str,
        api_key: str,
        source: str,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> Dict[str, str]:
        request_url = self._native_transport_runtime.apply_model_to_native_url(url, self.model)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type or "image/png",
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": self.max_output_tokens,
            },
        }
        resp = requests.post(
            request_url,
            json=payload,
            headers=self._native_transport_runtime.build_headers(request_url, api_key),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        raw = resp.text
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("vision provider returned invalid JSON") from exc
        candidates = obj.get("candidates") if isinstance(obj.get("candidates"), list) else []
        first = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        texts = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
            parts = content.get("parts") if isinstance(content.get("parts"), list) else []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = str(part.get("text", "") or "").strip()
                if text:
                    texts.append(text)
        raw_content = "\n".join(texts).strip()
        if not raw_content:
            raise RuntimeError("vision provider returned empty content")
        return {
            "content": raw_content,
            "finish_reason": self._normalize_finish_reason(first.get("finishReason")),
            "model": str(obj.get("modelVersion", "") or self.model),
            "request_source": source,
        }

    def _request_openai_multimodal(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> Dict[str, str]:
        url = self._resolve_openai_chat_url()
        api_key = self._resolve_primary_api_key()
        if not url or not api_key:
            raise RuntimeError("no_usable_openai_vision_provider")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.request_retry_attempts + 1):
            try:
                return self._post_openai_multimodal(
                    url=url,
                    api_key=api_key,
                    prompt=prompt,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                )
            except Exception as exc:
                last_exc = exc
                if not self._should_retry_transport_exception(exc) or attempt >= self.request_retry_attempts:
                    break
                self._bump_stat("request_retries")
                time.sleep(self._retry_sleep_seconds(attempt))
        raise last_exc or RuntimeError("vision provider returned empty response")

    def _post_openai_multimodal(
        self,
        *,
        url: str,
        api_key: str,
        prompt: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> Dict[str, str]:
        image_data = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type or 'image/png'};base64,{image_data}",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "smart-doc-flow-module2-vision/1.0",
                "Connection": "close",
            },
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        try:
            obj = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("vision provider returned invalid JSON") from exc
        choices = obj.get("choices") if isinstance(obj.get("choices"), list) else []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        raw_content = self._coerce_openai_content(message.get("content")).strip()
        if not raw_content:
            raise RuntimeError("vision provider returned empty content")
        return {
            "content": raw_content,
            "finish_reason": self._normalize_finish_reason(first.get("finish_reason")),
            "model": str(obj.get("model", "") or self.model),
            "request_source": "openai_chat_completions",
        }

    def _resolve_openai_chat_url(self) -> str:
        raw = str(
            self.base_url
            or os.getenv("MODULE2_GEMINI_VISION_BASE_URL", "")
            or os.getenv("MODULE2_LLM_BASE_URL", "")
            or os.getenv("MODULE2_LLM_API_BASE", "")
            or os.getenv("OPENAI_BASE_URL", "")
            or ""
        ).strip().rstrip("/")
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

    def _resolve_primary_native_url(self) -> str:
        raw = self._native_transport_runtime.resolve_native_url(self.model)
        if raw:
            return raw
        if self._allow_google_native_fallback():
            return self._native_transport_runtime.build_google_native_url(self.model)
        return ""

    def _resolve_primary_api_key(self) -> str:
        return str(self.api_key or self.native_api_key or "").strip()

    def _retry_sleep_seconds(self, attempt: int) -> float:
        attempt_value = max(1.0, float(attempt))
        return self.request_retry_backoff_sec * min(6.0, 1.35 ** (attempt_value - 1.0))

    @staticmethod
    def _should_retry_http_error(exc: HTTPError) -> bool:
        response = exc.response
        status = response.status_code if response is not None else None
        return bool(status in {408, 409, 425, 429} or (status is not None and status >= 500))

    def _should_retry_transport_exception(self, exc: Exception) -> bool:
        if isinstance(exc, HTTPError):
            return self._should_retry_http_error(exc)
        if isinstance(exc, RequestException):
            return self._is_retryable_request_error_text(str(exc))
        return self._is_retryable_request_error_text(f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _is_retryable_request_error_text(error_text: str) -> bool:
        raw = str(error_text or "").strip().lower()
        if not raw:
            return False
        retry_markers = (
            "ssleoferror",
            "unexpected eof",
            "eof occurred in violation of protocol",
            "connection aborted",
            "connection reset",
            "remote disconnected",
            "temporarily unavailable",
            "timed out",
            "timeout",
        )
        return any(marker in raw for marker in retry_markers)

    @staticmethod
    def _normalize_finish_reason(raw_reason: Any) -> str:
        reason = str(raw_reason or "").strip().upper()
        if reason in {"MAX_TOKENS", "LENGTH"}:
            return "length"
        if reason == "STOP":
            return "stop"
        return reason.lower()

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

    def _allow_google_native_fallback(self) -> bool:
        return False

    @staticmethod
    def _unique_texts(values: Any, *, limit: int, max_len: int = 180) -> list[str]:
        if not isinstance(values, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _has_nonempty_dataframe(payload: Dict[str, Any]) -> bool:
        dataframe = payload.get("dataframe") if isinstance(payload.get("dataframe"), dict) else {}
        rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        for row in rows:
            if isinstance(row, list) and any(str(cell or "").strip() for cell in row):
                return True
        return False

    @staticmethod
    def _dataframe_row_count(payload: Dict[str, Any]) -> int:
        dataframe = payload.get("dataframe") if isinstance(payload.get("dataframe"), dict) else {}
        rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        count = 0
        for row in rows:
            if isinstance(row, list) and any(str(cell or "").strip() for cell in row):
                count += 1
        return count

    @staticmethod
    def _dataframe_cell_count(payload: Dict[str, Any]) -> int:
        dataframe = payload.get("dataframe") if isinstance(payload.get("dataframe"), dict) else {}
        rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        count = 0
        for row in rows:
            if not isinstance(row, list):
                continue
            count += sum(1 for cell in row if str(cell or "").strip())
        return count

    @classmethod
    def _is_chart_like(cls, figure_obj: Dict[str, Any], context: Dict[str, Any]) -> bool:
        probe = " ".join(
            [
                str((context or {}).get("caption_hint", "") or ""),
                str((context or {}).get("nearby_text", "") or ""),
                str(figure_obj.get("title", "") or ""),
                str(figure_obj.get("caption", "") or ""),
                str(figure_obj.get("type", "") or ""),
            ]
        ).lower()
        if "photo" in probe and "chart" not in probe and "diagram" not in probe:
            return False
        chart_keywords = [
            "chart",
            "graph",
            "plot",
            "curve",
            "trend",
            "bar",
            "line",
            "pie",
            "histogram",
            "scatter",
            "distribution",
            "ratio",
            "rate",
            "year",
            "%",
            "图",
            "趋势",
            "增长",
            "占比",
            "比例",
            "分布",
        ]
        return any(keyword in probe for keyword in chart_keywords)

    @classmethod
    def _merge_figure_payload(cls, primary: Dict[str, Any], refined: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(primary)
        primary_type = str(primary.get("type", "") or "").strip().lower()
        refined_type = str(refined.get("type", "") or "").strip().lower()
        if refined_type and refined_type != "other" and primary_type in {"", "other"}:
            merged["type"] = refined_type

        for field in ("title", "caption"):
            if not str(merged.get(field, "") or "").strip() and str(refined.get(field, "") or "").strip():
                merged[field] = refined.get(field)

        primary_modes = cls._unique_texts(primary.get("content_modes"), limit=4, max_len=40)
        refined_modes = cls._unique_texts(refined.get("content_modes"), limit=4, max_len=40)
        merged["content_modes"] = (primary_modes + [x for x in refined_modes if x not in primary_modes])[:4]

        if cls._dataframe_cell_count(refined) > cls._dataframe_cell_count(primary):
            merged["dataframe"] = refined.get("dataframe")

        primary_key_values = primary.get("key_values") if isinstance(primary.get("key_values"), list) else []
        refined_key_values = refined.get("key_values") if isinstance(refined.get("key_values"), list) else []
        if refined_key_values and not primary_key_values:
            merged["key_values"] = refined_key_values[:8]

        merged["insights"] = cls._unique_texts(
            list(primary.get("insights") if isinstance(primary.get("insights"), list) else [])
            + list(refined.get("insights") if isinstance(refined.get("insights"), list) else []),
            limit=8,
        )
        merged["text_blocks"] = cls._unique_texts(
            list(primary.get("text_blocks") if isinstance(primary.get("text_blocks"), list) else [])
            + list(refined.get("text_blocks") if isinstance(refined.get("text_blocks"), list) else []),
            limit=8,
        )
        try:
            primary_conf = float(primary.get("confidence", 0.0) or 0.0)
        except Exception:
            primary_conf = 0.0
        try:
            refined_conf = float(refined.get("confidence", 0.0) or 0.0)
        except Exception:
            refined_conf = 0.0
        merged["confidence"] = max(primary_conf, refined_conf)
        return merged

    @classmethod
    def _should_refine_chart_extraction(
        cls,
        figure_obj: Dict[str, Any],
        context: Dict[str, Any],
        *,
        allow_refine: bool = True,
    ) -> bool:
        if not allow_refine:
            return False
        if not cls._is_chart_like(figure_obj, context):
            return False
        if cls._has_nonempty_dataframe(figure_obj):
            row_count = cls._dataframe_row_count(figure_obj)
            cell_count = cls._dataframe_cell_count(figure_obj)
            key_values = figure_obj.get("key_values") if isinstance(figure_obj.get("key_values"), list) else []
            if row_count >= 4 or cell_count >= 12:
                return False
            if row_count >= 2 and cell_count >= 8:
                return False
            if row_count >= 2 and len(key_values) >= 1:
                return False
        row_count = cls._dataframe_row_count(figure_obj)
        cell_count = cls._dataframe_cell_count(figure_obj)
        key_values = figure_obj.get("key_values") if isinstance(figure_obj.get("key_values"), list) else []
        if row_count <= 0 and cell_count <= 0 and len(key_values) <= 0:
            return True
        if row_count < 2 and cell_count < 6 and len(key_values) < 2:
            return True
        if row_count < 3 and cell_count < 8 and len(key_values) == 0:
            return True
        return False
        if cls._has_nonempty_dataframe(figure_obj):
            return False
        probe = " ".join(
            [
                str((context or {}).get("caption_hint", "") or ""),
                str((context or {}).get("nearby_text", "") or ""),
                str(figure_obj.get("title", "") or ""),
                str(figure_obj.get("caption", "") or ""),
                str(figure_obj.get("type", "") or ""),
            ]
        ).lower()
        if "photo" in probe:
            return False
        chart_keywords = [
            "chart",
            "graph",
            "plot",
            "curve",
            "trend",
            "bar",
            "line",
            "pie",
            "histogram",
            "distribution",
            "ratio",
            "rate",
            "year",
            "%",
            "图",
            "趋势",
            "增长",
            "占比",
            "比例",
            "分布",
        ]
        return any(keyword in probe for keyword in chart_keywords)

    @staticmethod
    def _infer_parse_mode(payload: Any) -> str:
        if isinstance(payload, dict):
            if isinstance(payload.get("figure"), dict):
                return "wrapped_figure"
            if isinstance(payload.get("table"), dict):
                return "wrapped_table"
            if any(k in payload for k in ("headers", "rows", "header_rows")):
                return "flat_table"
            if any(k in payload for k in ("caption", "type", "insights", "dataframe", "key_values")):
                return "flat_figure"
            return "object"
        if isinstance(payload, list):
            if payload and all(isinstance(item, dict) for item in payload[:8]):
                return "array_records"
            if payload and all(isinstance(item, list) for item in payload[:8]):
                return "array_rows"
            return "array"
        return "unknown"

    @classmethod
    def _extract_json_payload(cls, text: str) -> Optional[Any]:
        raw = str(text or "").strip()
        if not raw:
            return None

        candidates: list[str] = []
        fenced = cls._strip_fenced_json(raw)
        if fenced:
            candidates.append(fenced)
        candidates.append(raw)

        for candidate in candidates:
            loaded = cls._loads_json(candidate)
            if loaded is not None:
                return loaded
            repaired = cls._repair_truncated_json(candidate)
            if repaired:
                loaded = cls._loads_json(repaired)
                if loaded is not None:
                    return loaded
            for chunk in cls._iter_json_chunks(candidate):
                loaded = cls._loads_json(chunk)
                if loaded is not None:
                    return loaded
            if candidate.lstrip().startswith("["):
                records = []
                for chunk in cls._iter_container_chunks(candidate, "{", "}"):
                    loaded = cls._loads_json(chunk)
                    if isinstance(loaded, dict):
                        records.append(loaded)
                if records:
                    return records
        return None

    @staticmethod
    def _strip_fenced_json(raw: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", str(raw or ""), flags=re.IGNORECASE)
        if not match:
            return ""
        return str(match.group(1) or "").strip()

    @staticmethod
    def _loads_json(raw: str) -> Optional[Any]:
        try:
            return json.loads(str(raw or "").strip())
        except Exception:
            return None

    @classmethod
    def _repair_truncated_json(cls, raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return ""
        if text.startswith("["):
            records = []
            for chunk in cls._iter_container_chunks(text, "{", "}"):
                loaded = cls._loads_json(chunk)
                if isinstance(loaded, dict):
                    records.append(loaded)
            if records:
                return json.dumps(records, ensure_ascii=False)
        if text.startswith("{"):
            for chunk in cls._iter_container_chunks(text, "{", "}"):
                if chunk.startswith("{") and chunk.endswith("}"):
                    return chunk
        return ""

    @classmethod
    def _iter_json_chunks(cls, text: str) -> list[str]:
        chunks = []
        chunks.extend(cls._iter_container_chunks(text, "{", "}"))
        chunks.extend(cls._iter_container_chunks(text, "[", "]"))
        return chunks

    @staticmethod
    def _iter_container_chunks(text: str, open_ch: str, close_ch: str) -> list[str]:
        raw = str(text or "")
        out: list[str] = []
        depth = 0
        start: Optional[int] = None
        in_string = False
        escaped = False
        for idx, ch in enumerate(raw):
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == open_ch:
                if depth == 0:
                    start = idx
                depth += 1
                continue
            if ch == close_ch and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    out.append(raw[start : idx + 1])
                    start = None
        return out

    @classmethod
    def _normalize_payload_shape(cls, payload: Any, *, mode: str) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None
        if mode == "table":
            table = cls._normalize_table_candidate(payload)
            return {"table": table} if isinstance(table, dict) else None
        figure = cls._normalize_figure_candidate(payload)
        return {"figure": figure} if isinstance(figure, dict) else None

    @classmethod
    def _normalize_table_candidate(cls, payload: Any) -> Optional[Dict[str, Any]]:
        candidate = payload
        if isinstance(payload, dict) and isinstance(payload.get("table"), dict):
            candidate = payload.get("table")
        if isinstance(candidate, list):
            headers, rows = cls._rows_from_generic_list(candidate)
            if rows:
                return {
                    "headers": headers,
                    "rows": rows,
                    "confidence": 0.45,
                }
            return None
        if not isinstance(candidate, dict):
            return None
        normalized = dict(candidate)
        if not isinstance(normalized.get("headers"), list) and isinstance(normalized.get("columns"), list):
            normalized["headers"] = normalized.get("columns")
        if not isinstance(normalized.get("rows"), list) and isinstance(normalized.get("data"), list):
            normalized["rows"] = normalized.get("data")
        if not isinstance(normalized.get("rows"), list) and isinstance(normalized.get("table"), list):
            normalized["rows"] = normalized.get("table")
        if (not isinstance(normalized.get("headers"), list) or not isinstance(normalized.get("rows"), list)) and cls._is_scalar_record(normalized):
            headers, rows = cls._records_to_dataframe([normalized])
            normalized["headers"] = headers
            normalized["rows"] = rows
        return normalized

    @classmethod
    def _normalize_figure_candidate(cls, payload: Any) -> Optional[Dict[str, Any]]:
        candidate = payload
        if isinstance(payload, dict) and isinstance(payload.get("figure"), dict):
            candidate = payload.get("figure")
        if isinstance(candidate, list):
            headers, rows = cls._rows_from_generic_list(candidate)
            if not rows:
                return None
            return {
                "type": "chart",
                "content_modes": ["dataframe", "visual"],
                "dataframe": {
                    "headers": headers,
                    "rows": rows,
                },
                "insights": [],
                "text_blocks": [],
                "confidence": 0.55,
            }
        if not isinstance(candidate, dict):
            return None
        normalized = dict(candidate)
        if not isinstance(normalized.get("dataframe"), dict):
            if any(k in normalized for k in ("headers", "rows", "header_rows")):
                normalized["dataframe"] = {
                    "headers": normalized.get("headers") if isinstance(normalized.get("headers"), list) else [],
                    "rows": normalized.get("rows") if isinstance(normalized.get("rows"), list) else [],
                }
            elif cls._is_scalar_record(normalized):
                headers, rows = cls._records_to_dataframe([normalized])
                normalized["dataframe"] = {"headers": headers, "rows": rows}
        content_modes = normalized.get("content_modes")
        if not isinstance(content_modes, list):
            modes = []
            dataframe = normalized.get("dataframe") if isinstance(normalized.get("dataframe"), dict) else {}
            rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
            if rows:
                modes.append("dataframe")
            modes.append("visual")
            normalized["content_modes"] = modes[:4]
        return normalized

    @staticmethod
    def _is_scalar_record(payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict) or len(payload) < 2:
            return False
        reserved = {
            "figure",
            "table",
            "title",
            "caption",
            "type",
            "content_modes",
            "axes",
            "legend",
            "insights",
            "key_values",
            "dataframe",
            "topology",
            "text_blocks",
            "confidence",
            "headers",
            "rows",
            "header_rows",
            "notes",
            "units",
        }
        keys = [str(key or "").strip() for key in payload.keys()]
        if any(key in reserved for key in keys):
            return False
        scalar_count = 0
        for value in payload.values():
            if isinstance(value, (dict, list, tuple, set)):
                return False
            scalar_count += 1
        return scalar_count >= 2

    @classmethod
    def _rows_from_generic_list(cls, payload: list[Any]) -> tuple[list[str], list[list[str]]]:
        rows = [item for item in payload if item is not None]
        if not rows:
            return [], []
        if all(isinstance(item, dict) for item in rows[: min(8, len(rows))]):
            return cls._records_to_dataframe([dict(item) for item in rows if isinstance(item, dict)])
        if all(isinstance(item, list) for item in rows[: min(8, len(rows))]):
            matrix = []
            max_cols = 0
            for item in rows:
                if not isinstance(item, list):
                    continue
                vals = [str(cell or "").strip() for cell in item]
                if any(vals):
                    matrix.append(vals)
                    max_cols = max(max_cols, len(vals))
            headers = [f"col_{idx}" for idx in range(1, max_cols + 1)]
            return headers, matrix
        return ["value"], [[str(item or "").strip()] for item in rows if str(item or "").strip()]

    @staticmethod
    def _records_to_dataframe(records: list[Dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
        headers: list[str] = []
        seen: set[str] = set()
        for record in records:
            for key in record.keys():
                name = str(key or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                headers.append(name)
        table_rows: list[list[str]] = []
        for record in records:
            row = [str(record.get(header, "") or "").strip() for header in headers]
            if any(row):
                table_rows.append(row)
        return headers, table_rows

    def _build_cache_key(
        self,
        *,
        mode: str,
        prompt: str,
        image_bytes: bytes,
        context: Dict[str, Any],
    ) -> str:
        normalized_context = self._normalize_context_for_cache_key(context)
        digest = hashlib.sha256()
        digest.update(self.prompt_version.encode("utf-8"))
        digest.update(self.model.encode("utf-8"))
        digest.update(str(mode).encode("utf-8"))
        digest.update(self._normalize_prompt_for_cache_key(prompt).encode("utf-8", errors="ignore"))
        digest.update(image_bytes)
        digest.update(self._compact_json(normalized_context, max_chars=2500).encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _normalize_prompt_for_cache_key(prompt: str) -> str:
        marker = "Context:\n"
        prefix, separator, _ = str(prompt or "").partition(marker)
        if separator:
            return f"{prefix}{marker}<normalized>"
        return str(prompt or "")

    @classmethod
    def _normalize_context_for_cache_key(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        stable_context: Dict[str, Any] = {}
        for key in (
            "page",
            "object_type",
            "artifact_subtype",
            "caption_hint",
            "footnote_hint",
            "nearby_text",
            "primary_figure",
        ):
            normalized_value = cls._normalize_cache_value(context.get(key))
            if normalized_value in (None, "", [], {}):
                continue
            stable_context[str(key)] = normalized_value
        return stable_context

    @classmethod
    def _normalize_cache_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized: Dict[str, Any] = {}
            for raw_key in sorted(value.keys(), key=lambda item: str(item)):
                key = str(raw_key or "").strip()
                if not key or key in {"doc_name", "document_name", "file_name", "source_file_name", "domain_hints"}:
                    continue
                normalized_value = cls._normalize_cache_value(value.get(raw_key))
                if normalized_value in (None, "", [], {}):
                    continue
                normalized[key] = normalized_value
            return normalized
        if isinstance(value, list):
            normalized_list = [cls._normalize_cache_value(item) for item in value]
            return [item for item in normalized_list if item not in (None, "", [], {})]
        if isinstance(value, tuple):
            normalized_tuple = [cls._normalize_cache_value(item) for item in value]
            return [item for item in normalized_tuple if item not in (None, "", [], {})]
        if isinstance(value, set):
            normalized_set = [cls._normalize_cache_value(item) for item in sorted(value, key=lambda item: str(item))]
            return [item for item in normalized_set if item not in (None, "", [], {})]
        if isinstance(value, str):
            return value.strip()
        return value

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def _cache_put(self, key: str, payload: Dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    @staticmethod
    def _compact_json(payload: Dict[str, Any], *, max_chars: int) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = "{}"
        if len(text) > max_chars:
            return text[:max_chars]
        return text
