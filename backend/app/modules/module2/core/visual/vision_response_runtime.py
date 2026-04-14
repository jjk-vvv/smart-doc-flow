from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


NormalizeText = Callable[[str], str]


class VisionResponseRuntime:
    """Parse Gemini vision responses and normalize small insight payloads."""

    def __init__(self, *, normalize_text: NormalizeText) -> None:
        self._normalize_text = normalize_text

    @staticmethod
    def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None

        fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
        if fence:
            raw = fence.group(1).strip()

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape_next = False
            for index, ch in enumerate(raw[start:], start=start):
                if in_string:
                    if escape_next:
                        escape_next = False
                    elif ch == "\\":
                        escape_next = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = raw[start : index + 1]
                        try:
                            payload = json.loads(chunk)
                            if isinstance(payload, dict):
                                return payload
                        except json.JSONDecodeError:
                            pass

        starts = [idx for idx, ch in enumerate(raw) if ch == "{"] 
        ends = [idx for idx, ch in enumerate(raw) if ch == "}"]
        for start_idx in starts:
            for end_idx in reversed(ends):
                if end_idx <= start_idx:
                    continue
                chunk = raw[start_idx : end_idx + 1]
                try:
                    payload = json.loads(chunk)
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    continue
        return None

    @staticmethod
    def extract_candidate_text(raw: str) -> str:
        if not raw:
            return ""
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return ""

        texts: List[str] = []
        for candidate in obj.get("candidates", []):
            content = candidate.get("content", {}) if isinstance(candidate.get("content"), dict) else {}
            for part in content.get("parts", []):
                if not isinstance(part, dict):
                    continue
                text = str(part.get("text", "") or "").strip()
                if text:
                    texts.append(text)
        return "\n".join(texts)

    def extract_vision_insights(
        self,
        payload: Dict[str, Any],
        page_no: int,
        bbox_map: Dict[str, List[float]],
        *,
        max_insights: int = 4,
    ) -> List[Tuple[str, str]]:
        insights_raw = payload.get("insights", [])
        if not isinstance(insights_raw, list):
            return []

        existing = set(bbox_map.keys())
        out: List[Tuple[str, str]] = []
        for idx, item in enumerate(insights_raw[: max(0, int(max_insights or 0))], start=1):
            text = self._normalize_text(str(item or ""))
            if not text:
                continue
            ref_id = f"gv_p{page_no}_s{idx}"
            if ref_id in existing:
                continue
            out.append((ref_id, text))
        return out
