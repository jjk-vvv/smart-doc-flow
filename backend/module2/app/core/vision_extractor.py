from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


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
        self.prompt_version = "v2_visual_first_structured_rebuild"

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

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
            "\"axes\":{\"x\":\"\",\"y\":\"\"},"
            "\"legend\":[\"...\"],"
            "\"insights\":[\"...\"],"
            "\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],"
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
            return figure_obj
        if any(k in payload for k in ("caption", "type", "insights")):
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
        cache_key = self._build_cache_key(
            mode=mode,
            prompt=prompt,
            image_bytes=image_bytes,
            context=context,
        )
        if self.enable_cache and self.cache_dir is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

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
        result = self._request_json(url=url, payload=payload)
        if result is None and self.retry_count > 0:
            for _ in range(self.retry_count):
                result = self._request_json(url=url, payload=payload)
                if result is not None:
                    break
        if result is not None and self.enable_cache and self.cache_dir is not None:
            self._cache_put(cache_key, result)
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
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None

        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.replace("json", "", 1).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        starts = [i for i, ch in enumerate(raw) if ch == "{"]
        ends = [i for i, ch in enumerate(raw) if ch == "}"]
        for s in starts:
            for e in reversed(ends):
                if e <= s:
                    continue
                chunk = raw[s : e + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    continue
        return None

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
