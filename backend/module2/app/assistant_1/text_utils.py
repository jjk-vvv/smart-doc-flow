from __future__ import annotations

import hashlib
import json
import re
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

from ftfy import fix_text


_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_ASSISTANT1_UUID_NAMESPACE = uuid.UUID("9b2fb6bf-0a9f-4f4f-9cf6-7c7cb3f6b13d")


def repair_text(text: Any) -> str:
    value = str(text or "")
    if not value:
        return ""
    fixed = fix_text(value)
    fixed = fixed.replace("\r\n", "\n").replace("\r", "\n")
    return fixed.strip()


def normalize_text(text: Any) -> str:
    value = repair_text(text)
    value = _SPACE_RE.sub(" ", value)
    return value.strip()


def normalize_markdown_text(text: str) -> str:
    value = repair_text(text)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = _BLANK_RE.sub("\n\n", value)
    return value.strip()


def normalize_key(value: Any) -> str:
    text = normalize_text(value).lower()
    return re.sub(r"\s+", "", text)


def normalize_image_key(path_value: Any) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    return Path(raw.replace("\\", "/")).name.lower()


def caption_text(parts: Any) -> str:
    if isinstance(parts, str):
        return normalize_text(parts)
    if isinstance(parts, Iterable):
        texts = [normalize_text(item) for item in parts if normalize_text(item)]
        return " ".join(texts).strip()
    return ""


def similarity(a: Any, b: Any) -> float:
    left = normalize_key(a)
    right = normalize_key(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def bbox_to_xyxy(bbox: Sequence[float] | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    coords = list(bbox)
    if len(coords) == 5:
        _, x, y, w, h = coords
        return float(x), float(y), float(x + w), float(y + h)
    if len(coords) == 4:
        x1, y1, x2, y2 = coords
        return float(x1), float(y1), float(x2), float(y2)
    return None


def bbox_iou(left_bbox: Sequence[float] | None, right_bbox: Sequence[float] | None) -> float:
    left = bbox_to_xyxy(left_bbox)
    right = bbox_to_xyxy(right_bbox)
    if not left or not right:
        return 0.0
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    inter_x1 = max(lx1, rx1)
    inter_y1 = max(ly1, ry1)
    inter_x2 = min(lx2, rx2)
    inter_y2 = min(ly2, ry2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    left_area = max(0.0, lx2 - lx1) * max(0.0, ly2 - ly1)
    right_area = max(0.0, rx2 - rx1) * max(0.0, ry2 - ry1)
    denom = left_area + right_area - inter_area
    if denom <= 0:
        return 0.0
    return inter_area / denom


def stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps([str(part or "") for part in parts], ensure_ascii=False, sort_keys=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def stable_uuid(*parts: Any) -> str:
    payload = json.dumps([str(part or "") for part in parts], ensure_ascii=False, sort_keys=False)
    return str(uuid.uuid5(_ASSISTANT1_UUID_NAMESPACE, payload))


def escape_pipe(value: Any) -> str:
    text = normalize_text(value)
    return text.replace("|", "\\|")
