from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL | re.IGNORECASE)
WRITE_STATEMENTS = {"insert", "update", "delete", "merge", "alter", "drop", "create", "truncate", "grant", "revoke"}
READ_STATEMENTS = {"select", "with", "show", "explain"}


def extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty response")
    match = _JSON_BLOCK_RE.search(raw)
    candidate = match.group(1) if match else raw
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end >= start:
        candidate = candidate[start : end + 1]
    loaded = json.loads(candidate)
    if not isinstance(loaded, dict):
        raise ValueError("response is not a JSON object")
    return loaded


def quote_ident(name: str) -> str:
    cleaned = str(name or "").strip().replace('"', "")
    if not cleaned:
        raise ValueError("identifier is required")
    return f'"{cleaned}"'


def detect_statement_type(sql: str) -> str:
    text = str(sql or "").strip().lstrip("(").strip()
    if not text:
        return ""
    first = re.split(r"\s+", text, maxsplit=1)[0].lower()
    return first


def is_single_statement(sql: str) -> bool:
    text = str(sql or "").strip()
    if not text:
        return False
    body = text.rstrip().rstrip(";")
    return ";" not in body


def normalize_params(params: Any) -> list[Any]:
    if params is None:
        return []
    if isinstance(params, list):
        return params
    return [params]
