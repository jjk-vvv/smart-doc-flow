from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import requests
from requests.exceptions import HTTPError, RequestException

from .config import Assistant1Settings


def _normalize_base_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith("/v1/responses"):
        return cleaned[: -len("/v1/responses")]
    return cleaned


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


def _message_content_to_input_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: List[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type in {"text", "input_text", "output_text"}:
            parts.append(str(item.get("text") or ""))
            continue
        nested_text = item.get("text")
        if isinstance(nested_text, dict):
            parts.append(str(nested_text.get("value") or ""))
    return "".join(parts)


def chat_messages_to_responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    input_items: List[Dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user").strip().lower() or "user"
        if role not in {"system", "user", "assistant", "developer"}:
            role = "user"
        text = _message_content_to_input_text(message.get("content")).strip()
        if not text:
            continue
        input_items.append(
            {
                "role": role,
                "content": [
                    {
                        "type": "input_text",
                        "text": text,
                    }
                ],
            }
        )
    return input_items


@dataclass
class ResponsesFunctionCall:
    id: str
    call_id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""


@dataclass
class ResponsesCompletionResult:
    response_id: str
    status: str
    output_text: str
    function_calls: List[ResponsesFunctionCall] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


class Assistant1ResponsesProvider:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.base_url = _normalize_base_url(self.settings.chat_base_url)
        self.endpoint_path = str(self.settings.chat_endpoint_path or "/v1/responses").strip() or "/v1/responses"
        self.api_key = str(self.settings.chat_api_key or "").strip()
        self.model = str(self.settings.chat_model or "gpt-5-mini").strip() or "gpt-5-mini"
        self.temperature = float(self.settings.chat_temperature)
        self.timeout_sec = float(self.settings.chat_timeout_sec)
        self.max_output_tokens = int(self.settings.chat_max_output_tokens)
        self.reasoning_effort = str(self.settings.chat_reasoning_effort or "").strip().lower()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def complete(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        instructions: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str | Dict[str, Any] = "auto",
        max_output_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        text_verbosity: str = "",
        previous_response_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResponsesCompletionResult:
        if not self.configured:
            raise RuntimeError("assistant_1 responses provider is not configured")
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": input_items if input_items is not None else chat_messages_to_responses_input(messages or []),
            "max_output_tokens": int(max_output_tokens or self.max_output_tokens),
            "temperature": self.temperature,
        }
        instructions_text = str(instructions or "").strip()
        if instructions_text:
            payload["instructions"] = instructions_text
        verbosity = str(text_verbosity or "").strip().lower()
        if verbosity in {"low", "medium", "high"}:
            payload["text"] = {
                "format": {"type": "text"},
                "verbosity": verbosity,
            }
        effort = str(reasoning_effort or self.reasoning_effort or "").strip().lower()
        if effort in {"minimal", "low", "medium", "high"}:
            payload["reasoning"] = {"effort": effort}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        if metadata:
            payload["metadata"] = metadata
        data = self._request_json(payload)
        return self._parse_response(data)

    def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Exception | None = None
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            try:
                response = requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(),
                    timeout=self.timeout_sec,
                )
                response.raise_for_status()
                break
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if status not in retryable_statuses or attempt >= 2:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    raise RuntimeError(f"assistant_1 responses http error {status or 'unknown'}: {detail}") from exc
            except RequestException as exc:
                last_error = exc
                if attempt >= 2:
                    raise RuntimeError(f"assistant_1 responses connection error: {exc}") from exc
            time.sleep(0.8 * (attempt + 1))
        else:
            if last_error is not None:
                raise RuntimeError(f"assistant_1 responses connection error: {last_error}") from last_error
            raise RuntimeError("assistant_1 responses provider request failed without a response")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("assistant_1 responses provider returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("assistant_1 responses provider returned invalid JSON")
        return data

    def _request_url(self) -> str:
        if not self.configured:
            raise RuntimeError("assistant_1 responses provider is not configured")
        return f"{self.base_url}{self.endpoint_path}"

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "smart-doc-flow-assistant1/1.0",
        }

    @staticmethod
    def _parse_response(data: Dict[str, Any]) -> ResponsesCompletionResult:
        output_text_parts: List[str] = []
        function_calls: List[ResponsesFunctionCall] = []
        for item in data.get("output", []) if isinstance(data.get("output"), list) else []:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "message":
                for content_item in item.get("content", []) if isinstance(item.get("content"), list) else []:
                    if not isinstance(content_item, dict):
                        continue
                    if str(content_item.get("type") or "").strip().lower() == "output_text":
                        output_text_parts.append(str(content_item.get("text") or ""))
                continue
            if item_type == "function_call":
                raw_arguments = str(item.get("arguments") or "")
                function_calls.append(
                    ResponsesFunctionCall(
                        id=str(item.get("id") or ""),
                        call_id=str(item.get("call_id") or ""),
                        name=str(item.get("name") or ""),
                        arguments=_parse_tool_arguments(raw_arguments),
                        raw_arguments=raw_arguments,
                    )
                )
        return ResponsesCompletionResult(
            response_id=str(data.get("id") or ""),
            status=str(data.get("status") or ""),
            output_text="".join(output_text_parts).strip(),
            function_calls=function_calls,
            raw=data,
        )
