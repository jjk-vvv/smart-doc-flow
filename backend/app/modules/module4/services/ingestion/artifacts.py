from __future__ import annotations

import re
from typing import Any, Dict, List


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"raw": value}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _normalize_text(value: Any, *, max_len: int = 0) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if max_len > 0:
        return text[:max_len].strip()
    return text


def _normalize_text_list(value: Any, *, max_items: int = 6, max_len: int = 120) -> List[str]:
    items = value if isinstance(value, list) else []
    out: List[str] = []
    for item in items[: max(1, max_items)]:
        text = _normalize_text(item, max_len=max_len)
        if text and text not in out:
            out.append(text)
    return out


def _looks_placeholder_text(value: Any) -> bool:
    text = _normalize_text(value)
    if not text:
        return True
    meaningful = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text)
    if not meaningful:
        return True
    placeholder_count = text.count("?") + text.count("\uff1f") + text.count("\ufffd")
    return placeholder_count >= max(2, len(text) // 3)


def _strip_artifact_noise(
    value: Any,
    *,
    object_type: str = "",
    object_id: str = "",
    max_len: int = 0,
) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"^(chart|table|figure|image)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\uff08(](?:pdf|mineru|vision|vision|roi)[^\uff09)]*[\uff09)]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:pdf_mineru|vision_[a-z_]+|pdf_roi_crop|mineru_out)\b", "", text, flags=re.IGNORECASE)
    if object_id:
        text = re.sub(rf"\b{re.escape(object_id)}\b", "", text, flags=re.IGNORECASE)
    if object_type == "table":
        text = re.sub(r"^\s*\u8868\u683c\s*", "", text)
    elif object_type in {"figure", "image"}:
        text = re.sub(r"^\s*(?:\u56fe\u50cf|\u56fe\u7247|\u63d2\u56fe)\s*", "", text)
    text = re.sub(r"\b(?:table|figure|image|fig)[\s_-]*\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\u6807\u9898[:\uff1a]\s*", "", text)
    text = _normalize_text(text).strip("\xb7|:\uff1a;\uff1b,\uff0c- ")
    if max_len > 0:
        text = text[:max_len].strip()
    return text


def _shrink_dataframe(
    value: Any,
    *,
    max_rows: int = 6,
    max_cols: int = 6,
    max_cell_len: int = 120,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    headers = [
        _normalize_text(item, max_len=max_cell_len)
        for item in _as_list(value.get("headers"))[: max(1, max_cols)]
        if _normalize_text(item)
    ]
    rows: List[List[str]] = []
    for row in _as_list(value.get("rows"))[: max(1, max_rows)]:
        if not isinstance(row, list):
            continue
        cells = [_normalize_text(item, max_len=max_cell_len) for item in row[: max(1, max_cols)]]
        if any(cells):
            rows.append(cells)
    out: Dict[str, Any] = {}
    if headers:
        out["headers"] = headers
    if rows:
        out["rows"] = rows
    row_count = _to_int(value.get("row_count"), 0)
    col_count = _to_int(value.get("col_count"), 0)
    if row_count > 0:
        out["row_count"] = row_count
    if col_count > 0:
        out["col_count"] = col_count
    return out


def _artifact_kind_label(object_type: str) -> str:
    if object_type == "table":
        return "\u8868\u683c"
    if object_type in {"figure", "image"}:
        return "\u56fe\u50cf"
    return "\u8bc1\u636e"


def _looks_generic_artifact_name(text: str, object_type: str, object_id: str = "") -> bool:
    normalized = _normalize_text(text).strip()
    lower = normalized.lower()
    object_id_lower = _normalize_text(object_id).lower()
    if not normalized:
        return True
    if object_id_lower and lower == object_id_lower:
        return True
    if object_type == "table":
        return bool(
            lower in {"table", "\u8868\u683c", "\u8868"}
            or re.fullmatch(r"(table|\u8868\u683c)[\s_-]*\d+", lower)
            or lower.startswith("table ")
            or lower.startswith("\u8868\u683c ")
        )
    if object_type in {"figure", "image"}:
        return bool(
            lower in {"image", "figure", "fig", "\u56fe\u50cf", "\u56fe\u7247", "\u63d2\u56fe"}
            or re.fullmatch(r"(image|figure|fig|\u56fe\u50cf|\u56fe\u7247|\u63d2\u56fe)[\s_-]*\d+", lower)
            or len(normalized) <= 4
        )
    return False


def _looks_low_signal_artifact_text(text: str, object_type: str, object_id: str = "") -> bool:
    normalized = _normalize_text(text).strip()
    if not normalized or _looks_placeholder_text(normalized):
        return True
    cleaned = _strip_artifact_noise(normalized, object_type=object_type, object_id=object_id)
    if not cleaned or _looks_placeholder_text(cleaned):
        return True
    lower = cleaned.lower()
    object_id_lower = _normalize_text(object_id).lower()
    if object_id_lower and object_id_lower in lower:
        return True
    if re.search(r"\b(?:pdf|mineru|vision|vision|roi)\b", lower):
        return True
    return _looks_generic_artifact_name(cleaned, object_type, object_id)


def _artifact_headers_text(value: Any, *, object_type: str, object_id: str, max_items: int = 4) -> str:
    headers: List[str] = []
    for item in _as_list(value)[: max(1, max_items)]:
        text = _strip_artifact_noise(item, object_type=object_type, object_id=object_id, max_len=32)
        if not text or _looks_low_signal_artifact_text(text, object_type, object_id):
            continue
        if text not in headers:
            headers.append(text)
    return " | ".join(headers)


def _clean_artifact_text_list(
    value: Any,
    *,
    object_type: str,
    object_id: str,
    max_items: int = 6,
    max_len: int = 120,
) -> List[str]:
    out: List[str] = []
    for item in _as_list(value)[: max(1, max_items)]:
        text = _strip_artifact_noise(item, object_type=object_type, object_id=object_id, max_len=max_len)
        if not text or _looks_low_signal_artifact_text(text, object_type, object_id):
            continue
        if text not in out:
            out.append(text)
    return out


def _artifact_summary_snippet(
    *,
    object_type: str,
    object_id: str,
    raw_snippet: Any,
    locator: Dict[str, Any],
    page_no: Any,
) -> str:
    if object_type not in {"table", "figure", "image"}:
        return _normalize_text(raw_snippet, max_len=300)

    cleaned_raw = _strip_artifact_noise(raw_snippet, object_type=object_type, object_id=object_id, max_len=240)
    if cleaned_raw and not _looks_low_signal_artifact_text(cleaned_raw, object_type, object_id):
        return cleaned_raw

    if object_type == "table":
        preview_headers = _artifact_headers_text(
            _as_dict(locator.get("table_preview")).get("headers"),
            object_type=object_type,
            object_id=object_id,
            max_items=4,
        )
        if preview_headers:
            return f"\u8868\u5934\uff1a{preview_headers}"
        dataframe_headers = _artifact_headers_text(
            _as_dict(locator.get("dataframe")).get("headers"),
            object_type=object_type,
            object_id=object_id,
            max_items=4,
        )
        if dataframe_headers:
            return f"\u8868\u5934\uff1a{dataframe_headers}"

    summary_text = _strip_artifact_noise(
        locator.get("summary"),
        object_type=object_type,
        object_id=object_id,
        max_len=200,
    )
    if summary_text and not _looks_low_signal_artifact_text(summary_text, object_type, object_id):
        return summary_text

    title_or_caption = _strip_artifact_noise(
        locator.get("title") or locator.get("caption"),
        object_type=object_type,
        object_id=object_id,
        max_len=180,
    )
    if title_or_caption and not _looks_low_signal_artifact_text(title_or_caption, object_type, object_id):
        return title_or_caption

    key_points = _clean_artifact_text_list(
        locator.get("key_points"),
        object_type=object_type,
        object_id=object_id,
        max_items=2,
        max_len=72,
    )
    if key_points:
        return "\uff1b".join(key_points[:2])

    text_blocks = _clean_artifact_text_list(
        locator.get("text_blocks"),
        object_type=object_type,
        object_id=object_id,
        max_items=1,
        max_len=120,
    )
    if text_blocks:
        return text_blocks[0]

    page_value = _to_int(page_no, 0)
    if page_value > 0:
        return f"\u4f4d\u4e8e\u7b2c{page_value}\u9875"
    return ""


def _preferred_artifact_title_from_hit(hit_map: Dict[str, Any], object_type: str, object_id: str) -> str:
    locator = _as_dict(hit_map.get("locator"))
    raw_snippet = _normalize_text(hit_map.get("snippet"), max_len=180)
    snippet = _strip_artifact_noise(raw_snippet, object_type=object_type, object_id=object_id, max_len=180)
    candidates: List[str] = []
    if object_type == "table":
        preview = _as_dict(locator.get("table_preview"))
        preview_headers = _artifact_headers_text(
            preview.get("headers"),
            object_type=object_type,
            object_id=object_id,
            max_items=4,
        )
        if preview_headers:
            candidates.append(preview_headers)
        dataframe_headers = _artifact_headers_text(
            _as_dict(locator.get("dataframe")).get("headers"),
            object_type=object_type,
            object_id=object_id,
            max_items=4,
        )
        if dataframe_headers:
            candidates.append(dataframe_headers)
        candidates.extend(
            [
                _strip_artifact_noise(locator.get("title"), object_type=object_type, object_id=object_id, max_len=120),
                _strip_artifact_noise(locator.get("caption"), object_type=object_type, object_id=object_id, max_len=120),
                _strip_artifact_noise(locator.get("summary"), object_type=object_type, object_id=object_id, max_len=160),
            ]
        )
        if "\u6807\u9898\uff1a" in raw_snippet:
            candidates.append(raw_snippet.split("\u6807\u9898\uff1a", 1)[1])
        candidates.append(snippet)
    elif object_type in {"figure", "image"}:
        candidates.extend(
            [
                _strip_artifact_noise(locator.get("title"), object_type=object_type, object_id=object_id, max_len=120),
                _strip_artifact_noise(locator.get("caption"), object_type=object_type, object_id=object_id, max_len=120),
                _strip_artifact_noise(locator.get("summary"), object_type=object_type, object_id=object_id, max_len=160),
            ]
        )
        candidates.extend(
            _clean_artifact_text_list(
                locator.get("key_points"),
                object_type=object_type,
                object_id=object_id,
                max_items=2,
                max_len=72,
            )
        )
        candidates.extend(
            _clean_artifact_text_list(
                locator.get("text_blocks"),
                object_type=object_type,
                object_id=object_id,
                max_items=1,
                max_len=96,
            )
        )
        candidates.append(snippet)
    else:
        candidates.append(snippet)

    for candidate in candidates:
        text = _strip_artifact_noise(candidate, object_type=object_type, object_id=object_id, max_len=120)
        if text and not _looks_low_signal_artifact_text(text, object_type, object_id):
            return text
    return ""


def _choose_artifact_display_name(current: str, candidate: str, object_type: str, object_id: str) -> str:
    current_text = _normalize_text(current, max_len=120)
    candidate_text = _normalize_text(candidate, max_len=120)
    if not current_text:
        return candidate_text or current_text
    if not candidate_text:
        return current_text
    current_generic = _looks_low_signal_artifact_text(current_text, object_type, object_id)
    candidate_generic = _looks_low_signal_artifact_text(candidate_text, object_type, object_id)
    if current_generic and not candidate_generic:
        return candidate_text
    if not current_generic and candidate_generic:
        return current_text
    return candidate_text if len(candidate_text) > len(current_text) else current_text


def _build_artifact_node_display_name(hit_map: Dict[str, Any], object_type: str, object_id: str) -> str:
    label = _artifact_kind_label(object_type)
    title = _preferred_artifact_title_from_hit(hit_map, object_type, object_id)
    if title:
        return f"{label} \xb7 {title}"
    page_no = _to_int(hit_map.get("page"), 0)
    if page_no > 0:
        return f"{label} \xb7 P{page_no}"
    return object_id or label


def _artifact_display_name_from_attrs(
    display_name: str,
    *,
    node_type: str,
    attrs: Dict[str, Any],
) -> str:
    type_key = str(node_type or "").strip().lower()
    if type_key not in {"table", "figure", "image"}:
        return display_name

    object_id = str(attrs.get("object_id") or "").strip()
    if display_name and not _looks_low_signal_artifact_text(display_name, type_key, object_id):
        return display_name

    title = _strip_artifact_noise(
        attrs.get("title") or attrs.get("caption") or _as_dict(attrs.get("context")).get("caption_hint"),
        object_type=type_key,
        object_id=object_id,
        max_len=120,
    )
    if re.fullmatch(r"(?:\u4f4d\u4e8e)?\u7b2c\s*\d+\s*\u9875", title):
        title = ""
    label = _artifact_kind_label(type_key)
    if title and not _looks_low_signal_artifact_text(title, type_key, object_id):
        return f"{label} \xb7 {title}"

    page_value = _to_int(attrs.get("page") or _as_dict(attrs.get("context")).get("page"), 0)
    if page_value > 0:
        return f"{label} \xb7 P{page_value}"
    return label


def _normalize_artifact_attrs_for_response(node_type: str, attrs: Dict[str, Any]) -> Dict[str, Any]:
    type_key = str(node_type or "").strip().lower()
    if type_key not in {"table", "figure", "image"}:
        return attrs

    normalized = dict(attrs or {})
    object_id = str(normalized.get("object_id") or "").strip()
    locator_like = {
        "title": normalized.get("title"),
        "caption": normalized.get("caption"),
        "summary": normalized.get("summary"),
        "table_preview": normalized.get("table_preview"),
        "dataframe": normalized.get("dataframe_preview"),
        "key_points": normalized.get("key_points"),
        "text_blocks": normalized.get("text_blocks"),
    }

    title = _strip_artifact_noise(normalized.get("title"), object_type=type_key, object_id=object_id, max_len=120)
    caption = _strip_artifact_noise(normalized.get("caption"), object_type=type_key, object_id=object_id, max_len=160)
    summary = _strip_artifact_noise(normalized.get("summary"), object_type=type_key, object_id=object_id, max_len=200)
    if _looks_low_signal_artifact_text(title, type_key, object_id):
        title = ""
    if _looks_low_signal_artifact_text(caption, type_key, object_id):
        caption = ""
    if _looks_low_signal_artifact_text(summary, type_key, object_id):
        summary = ""

    snippet = _artifact_summary_snippet(
        object_type=type_key,
        object_id=object_id,
        raw_snippet=normalized.get("snippet"),
        locator=_as_dict(locator_like),
        page_no=normalized.get("page") or _as_dict(normalized.get("context")).get("page"),
    )

    context = _as_dict(normalized.get("context"))
    caption_hint = _strip_artifact_noise(
        context.get("caption_hint"),
        object_type=type_key,
        object_id=object_id,
        max_len=160,
    )
    if _looks_low_signal_artifact_text(caption_hint, type_key, object_id):
        caption_hint = title or caption or summary or snippet
    if caption_hint:
        context["caption_hint"] = caption_hint
    elif "caption_hint" in context:
        context.pop("caption_hint", None)

    normalized["title"] = title
    normalized["caption"] = caption
    normalized["summary"] = summary
    normalized["snippet"] = snippet
    normalized["key_points"] = _clean_artifact_text_list(
        normalized.get("key_points"),
        object_type=type_key,
        object_id=object_id,
        max_items=6,
        max_len=96,
    )
    normalized["text_blocks"] = _clean_artifact_text_list(
        normalized.get("text_blocks"),
        object_type=type_key,
        object_id=object_id,
        max_items=6,
        max_len=120,
    )
    normalized["context"] = {key: value for key, value in context.items() if value not in ("", None, [], {})}
    return {key: value for key, value in normalized.items() if value not in ("", None, [], {})}


def _merge_artifact_node_attrs(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in incoming.items():
        if key in {"key_points", "content_modes", "text_blocks"}:
            combined: List[str] = []
            for item in _normalize_text_list(merged.get(key), max_items=8) + _normalize_text_list(value, max_items=8):
                if item not in combined:
                    combined.append(item)
            if combined:
                merged[key] = combined
            continue
        if key == "context":
            context = _as_dict(merged.get("context"))
            for ctx_key, ctx_value in _as_dict(value).items():
                if ctx_value not in ("", None, [], {}):
                    context[ctx_key] = ctx_value
            if context:
                merged[key] = context
            continue
        if isinstance(value, dict):
            value_dict = _as_dict(value)
            if value_dict:
                merged[key] = value_dict
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
    return merged


def _build_artifact_node_attrs(
    *,
    file_hash: str,
    file_name: str,
    object_type: str,
    object_id: str,
    hit_map: Dict[str, Any],
) -> Dict[str, Any]:
    locator = _as_dict(hit_map.get("locator"))
    title = _preferred_artifact_title_from_hit(hit_map, object_type, object_id)
    caption = _strip_artifact_noise(locator.get("caption"), object_type=object_type, object_id=object_id, max_len=160)
    summary = _strip_artifact_noise(locator.get("summary"), object_type=object_type, object_id=object_id, max_len=200)
    if _looks_low_signal_artifact_text(caption, object_type, object_id):
        caption = ""
    if _looks_low_signal_artifact_text(summary, object_type, object_id):
        summary = ""
    table_preview = _shrink_dataframe(locator.get("table_preview"), max_rows=5, max_cols=6, max_cell_len=80)
    dataframe_preview = _shrink_dataframe(locator.get("dataframe"), max_rows=6, max_cols=6, max_cell_len=96)
    artifact_url = _normalize_text(hit_map.get("artifact_url"), max_len=320) or None
    ref_id = _normalize_text(hit_map.get("ref_id"), max_len=120) or None
    snippet = _artifact_summary_snippet(
        object_type=object_type,
        object_id=object_id,
        raw_snippet=hit_map.get("snippet"),
        locator=locator,
        page_no=hit_map.get("page"),
    )
    context = {
        "caption_hint": title or caption or summary or snippet,
        "page": hit_map.get("page"),
        "artifact_url": artifact_url,
        "ref_id": ref_id,
    }
    attrs: Dict[str, Any] = {
        "file_hash": file_hash,
        "file_name": file_name,
        "object_type": object_type,
        "object_id": object_id,
        "page": hit_map.get("page"),
        "ref_id": ref_id,
        "snippet": snippet,
        "artifact_url": artifact_url,
        "bbox": _as_list(hit_map.get("bbox")),
        "title": title,
        "caption": caption,
        "summary": summary,
        "table_preview": table_preview,
        "dataframe_preview": dataframe_preview,
        "dataframe_source": _normalize_text(locator.get("dataframe_source"), max_len=80),
        "artifact_source": _normalize_text(locator.get("artifact_source"), max_len=80),
        "figure_type": _normalize_text(locator.get("figure_type"), max_len=80),
        "key_points": _clean_artifact_text_list(
            locator.get("key_points"),
            object_type=object_type,
            object_id=object_id,
            max_items=6,
            max_len=96,
        ),
        "content_modes": _normalize_text_list(locator.get("content_modes"), max_items=6, max_len=48),
        "text_blocks": _clean_artifact_text_list(
            locator.get("text_blocks"),
            object_type=object_type,
            object_id=object_id,
            max_items=6,
            max_len=120,
        ),
        "context": {k: v for k, v in context.items() if v not in ("", None, [], {})},
    }
    topology = _as_dict(locator.get("topology"))
    if topology:
        attrs["topology"] = {
            "nodes": _as_list(topology.get("nodes"))[:20],
            "edges": _as_list(topology.get("edges"))[:30],
        }
    return {key: value for key, value in attrs.items() if value not in ("", None, [], {})}
