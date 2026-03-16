from __future__ import annotations

import json
from typing import Any, Iterable, List


def sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {str(event or 'message').strip()}\ndata: {payload}\n\n".encode("utf-8")


def chunk_text(text: str, chunk_size: int = 96) -> List[str]:
    raw = str(text or "")
    size = max(12, int(chunk_size or 96))
    if not raw:
        return []
    out: List[str] = []
    idx = 0
    while idx < len(raw):
        out.append(raw[idx : idx + size])
        idx += size
    return out


def join_non_empty(parts: Iterable[str], sep: str = "\n") -> str:
    return sep.join([str(part).strip() for part in parts if str(part or "").strip()]).strip()
