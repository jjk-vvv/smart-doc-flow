from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from app.assistant.provider import OpenAICompatibleChatProvider, resolve_llm_base_url


class GeminiVisionExtractor:
    """Gemini Vision JSON extractor with prompt layering and disk cache."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout_sec: float = 25.0,
        max_output_tokens: int = 4096,
        retry_count: int = 1,
        cache_dir: str | None = None,
        enable_cache: bool = True,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.max_output_tokens = max(512, int(max_output_tokens))
        self.retry_count = max(0, int(retry_count))
        self.enable_cache = bool(enable_cache)
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.prompt_version = "v3_visual_first_multimodal_structured"
        self._last_debug: Dict[str, Any] = {}
        self.reset_stats()

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    def reset_stats(self) -> None:
        self._stats = {
            "requests": 0,
            "cache_hits": 0,
            "provider_success": 0,
            "provider_failures": 0,
            "http_errors": 0,
            "parse_success": 0,
            "parse_failures": 0,
            "truncated_responses": 0,
        }
        self._last_debug = {}

    def get_stats_snapshot(self) -> Dict[str, Any]:
        return dict(self._stats)

    def get_last_debug(self) -> Dict[str, Any]:
        return dict(self._last_debug)

    def _bump_stat(self, key: str, amount: int = 1) -> None:
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
            "You are a high-precision table extraction engine for technical PDFs.\n"
            "Task: extract one table from this cropped ROI image.\n"
            "Internal layered workflow:\n"
            "1) Structural pass: identify header rows, merged headers, and data grid.\n"
            "2) Context pass: use provided context (caption/nearby text/domain hints) to disambiguate units and labels.\n"
            "3) Domain pass: preserve chemistry symbols, formulas, superscripts/subscripts, and Chinese statistical units.\n"
            "4) Validation pass: keep row/column order, do not invent values, keep blanks as empty strings.\n"
            "Rules:\n"
            "- Return strict JSON only, no markdown.\n"
            "- If confidence is low, still output best-effort structure with low confidence.\n"
            "- If unreadable, output empty arrays and confidence 0.0.\n"
            "Output schema:\n"
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
    ) -> Optional[Dict[str, Any]]:
        if not self.ready or not image_bytes:
            return None
        context_json = self._compact_json(context, max_chars=2000)
        prompt = (
            "You are a high-precision figure understanding engine for technical PDFs.\n"
            "Task: analyze one cropped figure/chart ROI image and output structured JSON.\n"
            "Internal layered workflow:\n"
            "1) Visual pass: identify figure type, title/caption, axes, legend, key entities.\n"
            "2) Modality pass: classify evidence channels from [dataframe, topology, text, visual].\n"
            "2) Context pass: inject nearby text and domain hints to resolve abbreviations.\n"
            "3) Consistency pass: keep only visible claims; no hallucination.\n"
            "Rules:\n"
            "- Return strict JSON only, no markdown.\n"
            "- Keep text concise and factual.\n"
            "Output schema:\n"
            "{"
            "\"figure\":{"
            "\"title\":\"\","
            "\"caption\":\"\","
            "\"type\":\"chart|diagram|photo|other\","
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
            if self._should_refine_chart_extraction(figure_obj, context):
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
            "You are a chart digitization engine for a single chart ROI image.\n"
            "Task: recover the best-effort dataframe from axes, legend, labels, bars, lines, slices, or annotated values.\n"
            "Rules:\n"
            "- Return strict JSON only, no markdown.\n"
            "- Prefer partial but grounded dataframe rows over prose.\n"
            "- Use only values visible in the image; do not invent hidden numbers.\n"
            "- If exact values are unreadable, keep dataframe empty but still return key_values and concise text_blocks.\n"
            "Output schema:\n"
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

        base_url = resolve_llm_base_url()
        if base_url:
            provider = OpenAICompatibleChatProvider(
                base_url=base_url,
                api_key=self.api_key,
                model=self.model,
                temperature=0.0,
                max_tokens=self.max_output_tokens,
                timeout_sec=self.timeout_sec,
            )
            if provider.configured:
                data_url = f"data:{mime_type or 'image/png'};base64,{base64.b64encode(image_bytes).decode('ascii')}"
                try:
                    result = provider.complete(
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                ],
                            }
                        ],
                        temperature=0.0,
                        max_tokens=self.max_output_tokens,
                    )
                    self._bump_stat("provider_success")
                    finish_reason = str(result.finish_reason or "").strip()
                    if finish_reason.lower() == "length":
                        self._bump_stat("truncated_responses")
                    raw_content = str(result.content or "").strip()
                    payload_value = self._extract_json_payload(raw_content)
                    payload = self._normalize_payload_shape(payload_value, mode=mode)
                    if payload is not None:
                        self._bump_stat("parse_success")
                        self._set_debug(
                            mode=mode,
                            status="ok",
                            request_source="openai_compatible",
                            finish_reason=finish_reason,
                            model=str(result.model or self.model),
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
                        request_source="openai_compatible",
                        finish_reason=finish_reason,
                        model=str(result.model or self.model),
                        parse_mode="unrecognized",
                        raw_excerpt=raw_content[:1200],
                        error="vision_response_unrecognized",
                    )
                except Exception as exc:
                    exc_text = f"{type(exc).__name__}: {exc}"
                    self._bump_stat("provider_failures")
                    if (
                        "http error" in exc_text.lower()
                        or "401" in exc_text
                        or "403" in exc_text
                        or "429" in exc_text
                    ):
                        self._bump_stat("http_errors")
                    self._set_debug(
                        mode=mode,
                        status="request_failed",
                        request_source="openai_compatible",
                        error=exc_text[:1200],
                    )

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(self.model, safe='')}:generateContent"
            f"?key={urllib.parse.quote(self.api_key, safe='')}"
        )
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
                "responseMimeType": "application/json",
            },
        }
        raw_result = self._request_json(url=url, payload=payload)
        if raw_result is None and self.retry_count > 0:
            for _ in range(self.retry_count):
                raw_result = self._request_json(url=url, payload=payload)
                if raw_result is not None:
                    break
        result = self._normalize_payload_shape(raw_result, mode=mode)
        if result is not None and self.enable_cache and self.cache_dir is not None:
            self._cache_put(cache_key, result)
        if result is not None:
            self._bump_stat("parse_success")
            self._set_debug(
                mode=mode,
                status="ok",
                request_source="google_native",
                parse_mode="object",
            )
        else:
            self._bump_stat("parse_failures")
            self._set_debug(
                mode=mode,
                status="parse_failed",
                request_source="google_native",
                error="vision_response_unrecognized",
            )
        return result

    def _request_json(self, *, url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _post(payload_obj: Dict[str, Any]) -> str:
            req = urllib.request.Request(
                url=url,
                data=json.dumps(payload_obj, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return resp.read().decode("utf-8", errors="ignore")

        try:
            raw = _post(payload)
        except urllib.error.HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            if status != 400:
                return None
            cfg = dict(payload.get("generationConfig", {}))
            cfg.pop("responseMimeType", None)
            retry_payload = dict(payload)
            retry_payload["generationConfig"] = cfg
            try:
                raw = _post(retry_payload)
            except Exception:
                return None
        except Exception:
            return None

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return None

        texts = []
        for candidate in obj.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
        if not texts:
            return None
        return self._extract_json_object("\n".join(texts))

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
        for row in rows[:8]:
            if isinstance(row, list) and any(str(cell or "").strip() for cell in row):
                return True
        return False

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

        if cls._has_nonempty_dataframe(refined) and not cls._has_nonempty_dataframe(primary):
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
    def _should_refine_chart_extraction(cls, figure_obj: Dict[str, Any], context: Dict[str, Any]) -> bool:
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
        digest = hashlib.sha256()
        digest.update(self.prompt_version.encode("utf-8"))
        digest.update(self.model.encode("utf-8"))
        digest.update(str(mode).encode("utf-8"))
        digest.update(prompt.encode("utf-8", errors="ignore"))
        digest.update(image_bytes)
        digest.update(self._compact_json(context, max_chars=2500).encode("utf-8"))
        return digest.hexdigest()

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
