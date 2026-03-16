from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ChatToolCall:
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatCompletionResult:
    content: str
    tool_calls: List[ChatToolCall] = field(default_factory=list)
    finish_reason: str = ""
    model: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_base_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/chat/completions"):
        return cleaned[: -len("/chat/completions")]
    return cleaned


def resolve_llm_base_url(explicit: Optional[str] = None) -> str:
    return _normalize_base_url(
        _first_non_empty(
            explicit,
            os.getenv("MODULE2_LLM_API_BASE", ""),
            os.getenv("MODULE2_GEMINI_API_BASE", ""),
            os.getenv("MODULE2_ASSISTANT_API_BASE", ""),
            os.getenv("OPENAI_BASE_URL", ""),
        )
    )


def resolve_llm_api_key(explicit: Optional[str] = None) -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_LLM_API_KEY", ""),
        os.getenv("MODULE2_GEMINI_API_KEY", ""),
        os.getenv("MODULE2_ASSISTANT_API_KEY", ""),
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    )


def resolve_llm_model(explicit: Optional[str] = None, *, default: str = "gemini-3-pro") -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_LLM_MODEL", ""),
        os.getenv("MODULE2_GEMINI_MODEL", ""),
        os.getenv("MODULE2_ASSISTANT_MODEL", ""),
        default,
    )


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: List[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            if item_type == "text":
                pieces.append(str(item.get("text", "") or ""))
                continue
            nested_text = item.get("text")
            if isinstance(nested_text, dict):
                pieces.append(str(nested_text.get("value", "") or ""))
        return "".join(pieces)
    return ""


def _parse_tool_arguments(raw_arguments: Any) -> Dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        return {}
    text = raw_arguments.strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {"value": loaded}
    except Exception:
        return {"raw": text}


def _extract_fenced_json_block(raw: str) -> str:
    text = str(raw or "").strip().lstrip("\ufeff")
    if not text:
        return ""
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1).strip()
    return text


def _iter_braced_json_candidates(raw: str) -> Iterable[str]:
    text = str(raw or "")
    if not text:
        return
    depth = 0
    start: Optional[int] = None
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue
        if ch == "}":
            if depth <= 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : idx + 1]
                start = None


def extract_json_object(text: Any) -> Optional[Dict[str, Any]]:
    raw = _normalize_content(text).strip() if not isinstance(text, str) else str(text).strip()
    if not raw:
        return None
    raw = _extract_fenced_json_block(raw)
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    for chunk in _iter_braced_json_candidates(raw):
        try:
            payload = json.loads(chunk)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
    return None


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout_sec: Optional[float] = None,
    ) -> None:
        env_base = (
            base_url
            or os.getenv("MODULE2_ASSISTANT_API_BASE", "")
            or os.getenv("MODULE2_LLM_API_BASE", "")
            or os.getenv("MODULE2_GEMINI_API_BASE", "")
            or os.getenv("OPENAI_BASE_URL", "")
        )
        env_key = (
            api_key
            or os.getenv("MODULE2_ASSISTANT_API_KEY", "")
            or os.getenv("MODULE2_LLM_API_KEY", "")
            or os.getenv("MODULE2_GEMINI_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
        )
        env_model = (
            model
            or os.getenv("MODULE2_ASSISTANT_MODEL", "")
            or os.getenv("MODULE2_LLM_MODEL", "")
            or os.getenv("MODULE2_GEMINI_MODEL", "gemini-3-pro")
        )
        env_temp = temperature if temperature is not None else float(os.getenv("MODULE2_ASSISTANT_TEMPERATURE", "0.2"))
        env_max_tokens = max_tokens if max_tokens is not None else int(os.getenv("MODULE2_ASSISTANT_MAX_TOKENS", "1600"))
        env_timeout = timeout_sec if timeout_sec is not None else float(os.getenv("MODULE2_ASSISTANT_TIMEOUT_SEC", "90"))

        self.base_url = _normalize_base_url(env_base)
        self.api_key = str(env_key or "").strip()
        self.model = str(env_model or "gemini-3-pro").strip() or "gemini-3-pro"
        self.temperature = max(0.0, min(1.0, float(env_temp)))
        self.max_tokens = max(256, int(env_max_tokens))
        self.timeout_sec = max(10.0, float(env_timeout))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def complete(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> ChatCompletionResult:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        if isinstance(response_format, dict) and response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        data = self._request_json(payload)
        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
        if not choices:
            raise RuntimeError("model returned no choices")
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        tool_calls_raw = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        tool_calls: List[ChatToolCall] = []
        for index, item in enumerate(tool_calls_raw):
            if not isinstance(item, dict):
                continue
            function_payload = item.get("function") if isinstance(item.get("function"), dict) else {}
            name = str(function_payload.get("name", "") or "").strip()
            if not name:
                continue
            tool_calls.append(
                ChatToolCall(
                    id=str(item.get("id", "") or f"tool-call-{index + 1}"),
                    name=name,
                    arguments=_parse_tool_arguments(function_payload.get("arguments")),
                )
            )
        return ChatCompletionResult(
            content=_normalize_content(message.get("content")),
            tool_calls=tool_calls,
            finish_reason=str(first.get("finish_reason", "") or ""),
            model=str(data.get("model", "") or self.model),
            raw=data,
        )

    def stream_text(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterable[str]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": True,
        }
        req = self._build_request(payload)
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") if isinstance(data.get("choices"), list) else []
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    text = _normalize_content(delta.get("content"))
                    if text:
                        yield text

    def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = self._build_request(payload)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"assistant provider http error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"assistant provider connection error: {exc.reason}") from exc
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("assistant provider returned invalid JSON")
        return data

    def _build_request(self, payload: Dict[str, Any]) -> urllib.request.Request:
        if not self.configured:
            raise RuntimeError("assistant provider is not configured")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
