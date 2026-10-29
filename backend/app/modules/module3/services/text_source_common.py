from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import requests

from .llm_service import _log_ai_api_exception, _log_ai_api_request, _log_ai_api_response


def log_event(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别文本文件编码: {path.name}")


def request_chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    api_url = f"{base_url}/chat/completions"
    try:
        _log_ai_api_request(api_url, payload, attempt=1, max_attempts=1)
        resp = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
        _log_ai_api_response(resp)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        _log_ai_api_exception(
            exc,
            close_call=not (
                isinstance(exc, requests.exceptions.HTTPError)
                and exc.response is not None
            ),
        )
        raise
    data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"chat/completions 返回异常: {json.dumps(data, ensure_ascii=False)[:600]}")

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        texts = [
            part.get("text")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if texts:
            return "\n".join(texts).strip()

    raise ValueError(f"无法解析 chat/completions 的输出: {json.dumps(data, ensure_ascii=False)[:600]}")


__all__ = ["log_event", "read_text_file", "request_chat_completions"]
