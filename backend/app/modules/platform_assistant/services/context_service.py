from __future__ import annotations

import json
from typing import Any, Iterable


def sanitize_text(value: str) -> str:
    return (
        str(value or "")
        .replace("\r", "")
        .replace("\u0000", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\uFFFD", "")
        .replace("*", "")
        .replace("`", "")
        .replace("#", "")
        .replace(">", "")
    )


def normalize_messages(raw_messages: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in raw_messages or []:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content[:4000]})
    return messages[-20:]


def _stringify_payload(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        raw = value
    else:
        try:
            raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            raw = str(value)
    return sanitize_text(raw)[:limit]


def summarize_context(raw_context: dict[str, Any] | None) -> str:
    if not raw_context:
        return ""

    lines: list[str] = []
    active_tab = sanitize_text(str(raw_context.get("activeTab") or "")).strip()
    page_cue = sanitize_text(str(raw_context.get("pageCue") or "")).strip()
    if active_tab:
        lines.append(f"activeTab: {active_tab}")
    if page_cue:
        lines.append(f"pageCue: {page_cue}")

    documents = raw_context.get("documents") or []
    for index, document in enumerate(documents[:3], start=1):
        lines.append(f"document[{index}]: {_stringify_payload(document, limit=800)}")

    selection = raw_context.get("selection")
    if selection:
        lines.append(f"selection: {_stringify_payload(selection, limit=600)}")

    module_status = raw_context.get("moduleStatus")
    if module_status:
        lines.append(f"moduleStatus: {_stringify_payload(module_status, limit=600)}")

    session_meta = raw_context.get("sessionMeta")
    if session_meta:
        lines.append(f"sessionMeta: {_stringify_payload(session_meta, limit=400)}")

    return "\n".join(filter(None, lines))[:6000]


__all__ = ["normalize_messages", "sanitize_text", "summarize_context"]
