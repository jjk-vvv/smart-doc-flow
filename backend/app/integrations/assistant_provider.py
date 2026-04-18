from __future__ import annotations

import json
import time
from typing import Any, Iterator

import requests
from requests import Response
from requests.exceptions import HTTPError, RequestException

from app.core.assistant_config import AssistantSettings


def _normalize_base_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    for suffix in ("/v1/responses", "/v1/chat/completions", "/chat/completions"):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
    return cleaned


def _messages_to_input_items(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    input_items: list[dict[str, Any]] = []
    for message in messages or []:
        role = str(message.get("role") or "user").strip().lower() or "user"
        if role not in {"user", "assistant", "system", "developer"}:
            role = "user"
        text = str(message.get("content") or "").strip()
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


def _normalize_chat_messages(
    messages: list[dict[str, Any]],
    *,
    instructions: str,
) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = []
    if str(instructions or "").strip():
        chat_messages.append({"role": "system", "content": str(instructions).strip()})

    for message in messages or []:
        role = str(message.get("role") or "user").strip().lower() or "user"
        if role not in {"user", "assistant", "system", "developer"}:
            role = "user"
        if role == "developer":
            role = "system"
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        chat_messages.append({"role": role, "content": content})
    return chat_messages


def _coerce_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type in {"text", "output_text", "input_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(value or "")


def _iter_sse_messages(response: Response) -> Iterator[tuple[str, str]]:
    current_event = ""
    current_data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=False):
        line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else str(raw_line or "")
        if not line:
            if current_event or current_data_lines:
                yield current_event or "message", "\n".join(current_data_lines).strip()
                current_event = ""
                current_data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
            continue
        if line.startswith("data:"):
            current_data_lines.append(line[len("data:") :].lstrip())
            continue
    if current_event or current_data_lines:
        yield current_event or "message", "\n".join(current_data_lines).strip()


class AssistantResponsesProvider:
    def __init__(self, settings: AssistantSettings | None = None) -> None:
        self.settings = settings or AssistantSettings.from_env()
        self.base_url = _normalize_base_url(self.settings.chat_base_url)
        self.endpoint_path = str(self.settings.chat_endpoint_path or "/v1/responses").strip() or "/v1/responses"
        self.api_key = str(self.settings.chat_api_key or "").strip()
        self.model = str(self.settings.chat_model or "gpt-5-mini").strip() or "gpt-5-mini"
        self.temperature = float(self.settings.chat_temperature)
        self.timeout_sec = float(self.settings.chat_timeout_sec)
        self.max_output_tokens = int(self.settings.chat_max_output_tokens)
        self.reasoning_effort = str(self.settings.chat_reasoning_effort or "").strip().lower()
        self.text_verbosity = str(self.settings.chat_text_verbosity or "").strip().lower()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def provider_info(self) -> dict[str, Any]:
        return {
            "baseUrl": self.base_url,
            "endpointPath": self.endpoint_path,
            "endpointStyle": self.settings.chat_endpoint_style,
            "model": self.model,
        }

    @property
    def uses_chat_completions_api(self) -> bool:
        return self.settings.chat_endpoint_style == "openai_chat_completions"

    def complete_text(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
    ) -> str:
        if not self.configured:
            raise RuntimeError("assistant responses provider is not configured")

        payload = self._build_payload(
            messages=messages,
            instructions=instructions,
            stream=False,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
        )
        data = self._request_json(payload)
        return self._extract_output_text(data, endpoint_style=self.settings.chat_endpoint_style)

    def stream_text(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
    ) -> Iterator[str]:
        if not self.configured:
            raise RuntimeError("assistant responses provider is not configured")

        payload = self._build_payload(messages=messages, instructions=instructions, stream=True)
        for data in self._iter_json_stream(payload):
            for delta in self._extract_stream_deltas(data):
                if delta:
                    yield delta

    def _build_payload(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        stream: bool,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
    ) -> dict[str, Any]:
        if self.uses_chat_completions_api:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": _normalize_chat_messages(messages, instructions=instructions),
                "max_tokens": int(max_output_tokens or self.max_output_tokens),
                "temperature": self.temperature,
            }
            if stream:
                payload["stream"] = True
            return payload

        payload: dict[str, Any] = {
            "model": self.model,
            "input": _messages_to_input_items(messages),
            "max_output_tokens": int(max_output_tokens or self.max_output_tokens),
            "temperature": self.temperature,
        }
        if stream:
            payload["stream"] = True
        if instructions.strip():
            payload["instructions"] = instructions.strip()
        effective_verbosity = str(text_verbosity or self.text_verbosity or "").strip().lower()
        if effective_verbosity in {"low", "medium", "high"}:
            payload["text"] = {
                "format": {"type": "text"},
                "verbosity": effective_verbosity,
            }
        effective_reasoning = str(reasoning_effort or self.reasoning_effort or "").strip().lower()
        if effective_reasoning in {"minimal", "low", "medium", "high"}:
            payload["reasoning"] = {"effort": effective_reasoning}
        return payload

    def _request_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        response: Response | None = None
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
                status_code = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if status_code not in retryable_statuses or attempt >= 2:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    raise RuntimeError(f"assistant responses http error {status_code or 'unknown'}: {detail}") from exc
            except RequestException as exc:
                last_error = exc
                if attempt >= 2:
                    raise RuntimeError(f"assistant responses connection error: {exc}") from exc
            time.sleep(0.8 * (attempt + 1))

        if response is None:
            raise RuntimeError(f"assistant responses connection error: {last_error}") from last_error

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("assistant responses provider returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("assistant responses provider returned invalid JSON")
        self._raise_if_error_payload(data)
        return data

    def _iter_json_stream(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(3):
            emitted_any = False
            try:
                with requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(),
                    timeout=self.timeout_sec,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    for _, data_text in _iter_sse_messages(response):
                        if not data_text:
                            continue
                        emitted_any = True
                        if data_text == "[DONE]":
                            return
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(data, dict):
                            continue
                        self._raise_if_error_payload(data)
                        event_type = str(data.get("type") or "").strip()
                        if event_type in {"response.failed", "error"}:
                            raise RuntimeError(str(data.get("message") or "assistant responses failed"))
                        yield data
                    return
            except HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if emitted_any or status_code not in retryable_statuses or attempt >= 2:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    raise RuntimeError(f"assistant responses http error {status_code or 'unknown'}: {detail}") from exc
            except RequestException as exc:
                last_error = exc
                if emitted_any or attempt >= 2:
                    raise RuntimeError(f"assistant responses connection error: {exc}") from exc
            time.sleep(0.8 * (attempt + 1))

        if last_error is not None:
            raise RuntimeError(f"assistant responses connection error: {last_error}") from last_error

    @staticmethod
    def _raise_if_error_payload(data: dict[str, Any]) -> None:
        error_payload = data.get("error")
        if isinstance(error_payload, dict):
            message = str(
                error_payload.get("message")
                or error_payload.get("type")
                or "assistant responses error"
            ).strip()
            raise RuntimeError(message)

    @staticmethod
    def _extract_output_text(data: dict[str, Any], *, endpoint_style: str = "openai_responses") -> str:
        if endpoint_style == "openai_chat_completions":
            choices = data.get("choices")
            if not isinstance(choices, list):
                return ""
            parts: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if not isinstance(message, dict):
                    continue
                parts.append(_coerce_text_content(message.get("content")))
            return "".join(parts).strip()

        parts: list[str] = []
        for item in data.get("output", []) if isinstance(data.get("output"), list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() != "message":
                continue
            for content_item in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if not isinstance(content_item, dict):
                    continue
                if str(content_item.get("type") or "").strip().lower() == "output_text":
                    parts.append(str(content_item.get("text") or ""))
        return "".join(parts).strip()

    def _extract_stream_deltas(self, data: dict[str, Any]) -> list[str]:
        if self.uses_chat_completions_api:
            choices = data.get("choices")
            if not isinstance(choices, list):
                return []
            deltas: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta_payload = choice.get("delta")
                if isinstance(delta_payload, dict):
                    content = _coerce_text_content(delta_payload.get("content"))
                    if content:
                        deltas.append(content)
                    continue
                message_payload = choice.get("message")
                if isinstance(message_payload, dict):
                    content = _coerce_text_content(message_payload.get("content"))
                    if content:
                        deltas.append(content)
            return deltas

        event_type = str(data.get("type") or "").strip()
        if event_type == "response.output_text.delta":
            delta = str(data.get("delta") or "")
            return [delta] if delta else []
        return []

    def _request_url(self) -> str:
        return f"{self.base_url}{self.endpoint_path}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "smart-doc-flow-assistant/1.0",
        }
