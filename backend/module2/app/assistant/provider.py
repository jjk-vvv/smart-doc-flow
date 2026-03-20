from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.exceptions import HTTPError, RequestException


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


@dataclass
class ChatStreamEvent:
    event: str
    text: str = ""
    reasoning_text: str = ""
    finish_reason: str = ""
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


def resolve_llm_model(explicit: Optional[str] = None, *, default: str = "gemini-3.1-pro") -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_LLM_MODEL", ""),
        os.getenv("MODULE2_GEMINI_MODEL", ""),
        os.getenv("MODULE2_ASSISTANT_MODEL", ""),
        default,
    )


def resolve_tuning_model(explicit: Optional[str] = None, *, default: str = "gemini-2.5-flash") -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_ASSISTANT_TUNING_MODEL", ""),
        default,
    )


def resolve_assistant_base_url(explicit: Optional[str] = None) -> str:
    return _normalize_base_url(
        _first_non_empty(
            explicit,
            os.getenv("MODULE2_ASSISTANT_API_BASE", ""),
            os.getenv("MODULE2_LLM_API_BASE", ""),
            os.getenv("MODULE2_GEMINI_API_BASE", ""),
            os.getenv("OPENAI_BASE_URL", ""),
        )
    )


def resolve_assistant_api_key(explicit: Optional[str] = None) -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_ASSISTANT_API_KEY", ""),
        os.getenv("MODULE2_LLM_API_KEY", ""),
        os.getenv("MODULE2_GEMINI_API_KEY", ""),
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    )


def resolve_assistant_model(explicit: Optional[str] = None, *, default: str = "gemini-2.5-flash") -> str:
    return _first_non_empty(
        explicit,
        os.getenv("MODULE2_ASSISTANT_MODEL", ""),
        os.getenv("MODULE2_LLM_MODEL", ""),
        os.getenv("MODULE2_GEMINI_MODEL", ""),
        default,
    )


def build_module2_llm_provider(
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout_sec: Optional[float] = None,
) -> "OpenAICompatibleChatProvider":
    return OpenAICompatibleChatProvider(
        base_url=resolve_llm_base_url(base_url),
        api_key=resolve_llm_api_key(api_key),
        model=resolve_llm_model(model, default="gemini-3.1-pro"),
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
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
        env_base = resolve_assistant_base_url(base_url)
        env_key = resolve_assistant_api_key(api_key)
        env_model = resolve_assistant_model(model)
        env_temp = temperature if temperature is not None else float(os.getenv("MODULE2_ASSISTANT_TEMPERATURE", "0.2"))
        env_max_tokens = max_tokens if max_tokens is not None else int(os.getenv("MODULE2_ASSISTANT_MAX_TOKENS", "1600"))
        env_timeout = timeout_sec if timeout_sec is not None else float(os.getenv("MODULE2_ASSISTANT_TIMEOUT_SEC", "90"))

        self.base_url = _normalize_base_url(env_base)
        self.api_key = str(env_key or "").strip()
        self.model = str(env_model or "gemini-3.1-pro").strip() or "gemini-3.1-pro"
        self.temperature = max(0.0, min(1.0, float(env_temp)))
        self.max_tokens = max(256, int(env_max_tokens))
        self.timeout_sec = max(10.0, float(env_timeout))
        self.retry_attempts = max(1, int(os.getenv("MODULE2_ASSISTANT_PROVIDER_RETRY_ATTEMPTS", "2")))
        self.retry_backoff_sec = max(0.2, float(os.getenv("MODULE2_ASSISTANT_PROVIDER_RETRY_BACKOFF_SEC", "1.0")))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def healthcheck(self, *, timeout_sec: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with exactly: ok",
                },
                {
                    "role": "user",
                    "content": "ping",
                },
            ],
            "temperature": 0,
            "max_tokens": 8,
            "stream": False,
        }
        data = self._request_json(payload, timeout_sec=timeout_sec)
        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
        if not choices:
            raise RuntimeError("assistant provider healthcheck returned no choices")
        return {
            "ok": True,
            "base_url": self.base_url,
            "model": str(data.get("model", "") or self.model),
            "checked_at": time.time(),
        }

    def complete(
        self,
        *,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
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
        reasoning_value = str(reasoning_effort or "").strip().lower()
        if reasoning_value in {"minimal", "low", "medium", "high"}:
            payload["reasoning_effort"] = reasoning_value
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
        reasoning_effort: Optional[str] = None,
    ) -> Iterable[str]:
        for event in self.stream_events(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ):
            if event.event == "content_delta" and event.text:
                yield event.text

    def stream_events(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> Iterable[ChatStreamEvent]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": True,
        }
        reasoning_value = str(reasoning_effort or "").strip().lower()
        if reasoning_value in {"minimal", "low", "medium", "high"}:
            payload["reasoning_effort"] = reasoning_value
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(),
                    timeout=self.timeout_sec,
                    stream=True,
                ) as resp:
                    resp.raise_for_status()
                    resp.encoding = "utf-8"
                    yield ChatStreamEvent(event="stream_opened", raw={"status": resp.status_code, "attempt": attempt})
                    for raw_line in resp.iter_lines(decode_unicode=False):
                        if isinstance(raw_line, bytes):
                            line = raw_line.decode("utf-8", errors="ignore").strip()
                        else:
                            line = str(raw_line or "").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        if data_str == "[DONE]":
                            yield ChatStreamEvent(event="finish", finish_reason="done", raw={"done": True, "attempt": attempt})
                            return
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(data.get("error"), dict):
                            error_payload = data.get("error") or {}
                            message = str(error_payload.get("message") or error_payload.get("type") or "unknown stream error").strip()
                            raise RuntimeError(f"assistant provider stream error: {message}")
                        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            yield ChatStreamEvent(event="frame_received", raw=data)
                            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                            text = _normalize_content(delta.get("content"))
                            reasoning_text = _normalize_content(delta.get("reasoning_content"))
                            finish_reason = str(choice.get("finish_reason", "") or "").strip()
                            if reasoning_text:
                                yield ChatStreamEvent(
                                    event="reasoning_delta",
                                    reasoning_text=reasoning_text,
                                    raw=data,
                                )
                            if text:
                                yield ChatStreamEvent(
                                    event="content_delta",
                                    text=text,
                                    raw=data,
                                )
                            if finish_reason:
                                yield ChatStreamEvent(
                                    event="finish",
                                    finish_reason=finish_reason,
                                    raw=data,
                                )
                    return
            except HTTPError as exc:
                last_error = exc
                if not self._should_retry_http_error(exc) or attempt >= self.retry_attempts:
                    response = exc.response
                    status = response.status_code if response is not None else "unknown"
                    detail = response.text if response is not None else str(exc)
                    raise RuntimeError(f"assistant provider http error {status}: {detail}") from exc
                time.sleep(self._retry_sleep_seconds(attempt))
            except RequestException as exc:
                last_error = exc
                if not self._should_retry_request_exception(exc) or attempt >= self.retry_attempts:
                    raise RuntimeError(f"assistant provider connection error: {exc}") from exc
                time.sleep(self._retry_sleep_seconds(attempt))
        if last_error is not None:
            raise RuntimeError(f"assistant provider connection error: {last_error}")

    def _request_json(self, payload: Dict[str, Any], *, timeout_sec: Optional[float] = None) -> Dict[str, Any]:
        resp = None
        last_error: Optional[BaseException] = None
        resolved_timeout = self.timeout_sec if timeout_sec is None else max(5.0, float(timeout_sec))
        for attempt in range(1, self.retry_attempts + 1):
            try:
                resp = requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(),
                    timeout=resolved_timeout,
                )
                resp.raise_for_status()
                break
            except HTTPError as exc:
                last_error = exc
                if not self._should_retry_http_error(exc) or attempt >= self.retry_attempts:
                    response = exc.response
                    status = response.status_code if response is not None else "unknown"
                    detail = response.text if response is not None else str(exc)
                    raise RuntimeError(f"assistant provider http error {status}: {detail}") from exc
                time.sleep(self._retry_sleep_seconds(attempt))
            except RequestException as exc:
                last_error = exc
                if not self._should_retry_request_exception(exc) or attempt >= self.retry_attempts:
                    raise RuntimeError(f"assistant provider connection error: {exc}") from exc
                time.sleep(self._retry_sleep_seconds(attempt))
        if resp is None:
            raise RuntimeError(f"assistant provider connection error: {last_error or 'unknown error'}")
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("assistant provider returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("assistant provider returned invalid JSON")
        return data

    def _request_url(self) -> str:
        if not self.configured:
            raise RuntimeError("assistant provider is not configured")
        return f"{self.base_url}/chat/completions"

    def _build_headers(self) -> Dict[str, str]:
        if not self.configured:
            raise RuntimeError("assistant provider is not configured")
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "smart-doc-flow-module2/1.0",
        }

    def _retry_sleep_seconds(self, attempt: int) -> float:
        return self.retry_backoff_sec * max(1.0, float(attempt))

    @staticmethod
    def _should_retry_http_error(exc: HTTPError) -> bool:
        response = exc.response
        status = response.status_code if response is not None else None
        return bool(status in {408, 409, 425, 429} or (status is not None and status >= 500))

    @staticmethod
    def _should_retry_request_exception(exc: RequestException) -> bool:
        raw = str(exc or "").strip().lower()
        retry_markers = (
            "ssleoferror",
            "unexpected eof",
            "eof occurred in violation of protocol",
            "connection aborted",
            "connection reset",
            "remote disconnected",
            "temporarily unavailable",
            "timed out",
            "timeout",
        )
        return any(marker in raw for marker in retry_markers) or not raw
