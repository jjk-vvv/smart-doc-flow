from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

import requests
from requests import Response
from requests.exceptions import HTTPError, RequestException

from .chat_completions_codec import (
    build_chat_completion_payload,
    clone_json,
    normalize_chat_message_list,
    parse_chat_completions_response,
    tool_outputs_to_chat_messages,
)
from .config import Assistant1Settings


def _normalize_base_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    for suffix in ("/v1/responses", "/v1/chat/completions"):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
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


def _iter_sse_messages(response: Response) -> Iterator[tuple[str, str]]:
    current_event = ""
    current_data_lines: List[str] = []
    for raw_line in response.iter_lines(decode_unicode=False):
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="ignore")
        else:
            line = str(raw_line or "")
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


@dataclass
class ResponsesStreamEvent:
    event: str
    type: str
    response_id: str = ""
    response_status: str = ""
    output_text_delta: str = ""
    output_text: str = ""
    function_call: Optional[ResponsesFunctionCall] = None
    item_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class Assistant1ResponsesProvider:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.base_url = _normalize_base_url(self.settings.chat_base_url)
        self.endpoint_path = str(self.settings.chat_endpoint_path or "/v1/responses").strip() or "/v1/responses"
        self.endpoint_style = str(self.settings.chat_endpoint_style or "openai_responses").strip().lower()
        self.api_key = str(self.settings.chat_api_key or "").strip()
        self.model = str(self.settings.chat_model or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        self.temperature = float(self.settings.chat_temperature)
        self.timeout_sec = float(self.settings.chat_timeout_sec)
        self.max_output_tokens = int(self.settings.chat_max_output_tokens)
        self.reasoning_effort = str(self.settings.chat_reasoning_effort or "").strip().lower()
        self._chat_state_lock = threading.Lock()
        self._chat_state_by_response_id: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        self._chat_state_limit = 96

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
        if self._use_chat_completions():
            return self._complete_with_chat_completions(
                messages=messages,
                input_items=input_items,
                instructions=instructions,
                tools=tools,
                tool_choice=tool_choice,
                max_output_tokens=max_output_tokens,
                previous_response_id=previous_response_id,
                metadata=metadata,
            )
        payload = self._build_payload(
            messages=messages,
            input_items=input_items,
            instructions=instructions,
            tools=tools,
            tool_choice=tool_choice,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            previous_response_id=previous_response_id,
            metadata=metadata,
            stream=False,
        )
        data = self._request_json(payload)
        return self._parse_response(data)

    def stream_events(
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
    ) -> Iterator[ResponsesStreamEvent]:
        if not self.configured:
            raise RuntimeError("assistant_1 responses provider is not configured")
        if self._use_chat_completions():
            yield from self._stream_events_with_chat_completions(
                messages=messages,
                input_items=input_items,
                instructions=instructions,
                tools=tools,
                tool_choice=tool_choice,
                max_output_tokens=max_output_tokens,
                previous_response_id=previous_response_id,
                metadata=metadata,
            )
            return
        payload = self._build_payload(
            messages=messages,
            input_items=input_items,
            instructions=instructions,
            tools=tools,
            tool_choice=tool_choice,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            previous_response_id=previous_response_id,
            metadata=metadata,
            stream=True,
        )
        last_error: Exception | None = None
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            emitted_any = False
            try:
                with requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(stream=True),
                    timeout=self.timeout_sec,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    latest_response_id = ""
                    latest_status = ""
                    function_calls_by_item_id: Dict[str, ResponsesFunctionCall] = {}
                    for _, data_text in _iter_sse_messages(response):
                        if not data_text:
                            continue
                        emitted_any = True
                        if data_text == "[DONE]":
                            yield ResponsesStreamEvent(
                                event="response.done",
                                type="response.done",
                                response_id=latest_response_id,
                                response_status=latest_status,
                                raw={"done": True},
                            )
                            return
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(data, dict):
                            continue
                        if isinstance(data.get("error"), dict):
                            error_payload = data.get("error") or {}
                            message = str(
                                error_payload.get("message")
                                or error_payload.get("type")
                                or "assistant_1 responses stream error"
                            ).strip()
                            raise RuntimeError(message)
                        event = self._parse_stream_event(
                            data=data,
                            latest_response_id=latest_response_id,
                            latest_status=latest_status,
                            function_calls_by_item_id=function_calls_by_item_id,
                        )
                        if event.response_id:
                            latest_response_id = event.response_id
                        if event.response_status:
                            latest_status = event.response_status
                        yield event
                    return
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if emitted_any or status not in retryable_statuses or attempt >= 2:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    raise RuntimeError(f"assistant_1 responses http error {status or 'unknown'}: {detail}") from exc
            except RequestException as exc:
                last_error = exc
                if emitted_any or attempt >= 2:
                    raise RuntimeError(f"assistant_1 responses connection error: {exc}") from exc
            time.sleep(0.8 * (attempt + 1))
        if last_error is not None:
            raise RuntimeError(f"assistant_1 responses connection error: {last_error}") from last_error

    def _build_payload(
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
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": input_items if input_items is not None else chat_messages_to_responses_input(messages or []),
            "max_output_tokens": int(max_output_tokens or self.max_output_tokens),
            "temperature": self.temperature,
        }
        if stream:
            payload["stream"] = True
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
        return payload

    def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Exception | None = None
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            try:
                response = requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(stream=False),
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

    def _build_headers(self, *, stream: bool) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream" if stream else "application/json",
            "User-Agent": "smart-doc-flow-assistant1/1.0",
        }

    def _use_chat_completions(self) -> bool:
        return self.endpoint_style == "openai_chat_completions"

    def _complete_with_chat_completions(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        instructions: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str | Dict[str, Any] = "auto",
        max_output_tokens: Optional[int] = None,
        previous_response_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResponsesCompletionResult:
        request_messages = self._build_chat_completion_messages(
            messages=messages,
            input_items=input_items,
            instructions=instructions,
            previous_response_id=previous_response_id,
        )
        payload = build_chat_completion_payload(
            model=self.model,
            request_messages=request_messages,
            temperature=self.temperature,
            max_output_tokens=int(max_output_tokens or self.max_output_tokens),
            tools=tools,
            tool_choice=tool_choice,
            metadata=metadata,
            stream=False,
        )
        data = self._request_json(payload)
        parsed = parse_chat_completions_response(
            data,
            message_content_to_text=_message_content_to_input_text,
            parse_tool_arguments=_parse_tool_arguments,
        )
        function_calls = [
            ResponsesFunctionCall(
                id=str(item.get("id") or ""),
                call_id=str(item.get("call_id") or ""),
                name=str(item.get("name") or ""),
                arguments=item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                raw_arguments=str(item.get("raw_arguments") or ""),
            )
            for item in parsed.get("function_calls", [])
            if isinstance(item, dict)
        ]
        self._remember_chat_state(
            str(parsed.get("response_id") or ""),
            request_messages,
            parsed.get("assistant_message") if isinstance(parsed.get("assistant_message"), dict) else None,
        )
        return ResponsesCompletionResult(
            response_id=str(parsed.get("response_id") or ""),
            status=str(parsed.get("status") or ""),
            output_text=str(parsed.get("output_text") or ""),
            function_calls=function_calls,
            raw=data,
        )

    def _build_chat_completion_messages(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]],
        input_items: Optional[List[Dict[str, Any]]],
        instructions: str,
        previous_response_id: str,
    ) -> List[Dict[str, Any]]:
        if messages is not None:
            request_messages = normalize_chat_message_list(
                messages,
                instructions=instructions,
                message_content_to_text=_message_content_to_input_text,
            )
        elif previous_response_id:
            request_messages = self._load_chat_state(previous_response_id)
        else:
            request_messages = normalize_chat_message_list(
                [],
                instructions=instructions,
                message_content_to_text=_message_content_to_input_text,
            )

        if input_items:
            if not request_messages:
                raise RuntimeError("chat completions tool outputs require prior message context")
            request_messages.extend(tool_outputs_to_chat_messages(input_items))
        return request_messages

    def _remember_chat_state(
        self,
        response_id: str,
        request_messages: List[Dict[str, Any]],
        assistant_message: Dict[str, Any] | None,
    ) -> None:
        if not response_id:
            return
        transcript = clone_json(request_messages)
        if assistant_message and self._chat_message_has_payload(assistant_message):
            transcript.append(clone_json(assistant_message))
        with self._chat_state_lock:
            self._chat_state_by_response_id[response_id] = transcript
            self._chat_state_by_response_id.move_to_end(response_id)
            while len(self._chat_state_by_response_id) > self._chat_state_limit:
                self._chat_state_by_response_id.popitem(last=False)

    def _load_chat_state(self, response_id: str) -> List[Dict[str, Any]]:
        with self._chat_state_lock:
            transcript = self._chat_state_by_response_id.get(response_id)
            if transcript is None:
                raise RuntimeError(f"chat completions state not found for previous_response_id={response_id}")
            self._chat_state_by_response_id.move_to_end(response_id)
            return clone_json(transcript)

    @staticmethod
    def _chat_message_has_payload(message: Dict[str, Any]) -> bool:
        if not isinstance(message, dict):
            return False
        if str(message.get("content") or "").strip():
            return True
        return isinstance(message.get("tool_calls"), list) and bool(message.get("tool_calls"))

    def _stream_events_with_chat_completions(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
        instructions: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str | Dict[str, Any] = "auto",
        max_output_tokens: Optional[int] = None,
        previous_response_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Iterator[ResponsesStreamEvent]:
        request_messages = self._build_chat_completion_messages(
            messages=messages,
            input_items=input_items,
            instructions=instructions,
            previous_response_id=previous_response_id,
        )
        payload = build_chat_completion_payload(
            model=self.model,
            request_messages=request_messages,
            temperature=self.temperature,
            max_output_tokens=int(max_output_tokens or self.max_output_tokens),
            tools=tools,
            tool_choice=tool_choice,
            metadata=metadata,
            stream=True,
        )
        last_error: Exception | None = None
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            emitted_any = False
            try:
                with requests.post(
                    self._request_url(),
                    json=payload,
                    headers=self._build_headers(stream=True),
                    timeout=self.timeout_sec,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    response_id = ""
                    final_status = "in_progress"
                    yielded_created = False
                    text_parts: List[str] = []
                    tool_state_by_index: Dict[int, Dict[str, Any]] = {}

                    for _, data_text in _iter_sse_messages(response):
                        if not data_text:
                            continue
                        emitted_any = True
                        if data_text == "[DONE]":
                            break
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(data, dict):
                            continue
                        if isinstance(data.get("error"), dict):
                            error_payload = data.get("error") or {}
                            message = str(
                                error_payload.get("message")
                                or error_payload.get("type")
                                or "assistant_1 chat completions stream error"
                            ).strip()
                            raise RuntimeError(message)

                        response_id = str(data.get("id") or response_id or "")
                        if response_id and not yielded_created:
                            yielded_created = True
                            yield ResponsesStreamEvent(
                                event="response.created",
                                type="response.created",
                                response_id=response_id,
                                response_status="in_progress",
                                raw=data,
                            )

                        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                            finish_reason = str(choice.get("finish_reason") or "").strip().lower()
                            if finish_reason:
                                final_status = "completed" if finish_reason in {"stop", "tool_calls"} else "incomplete"

                            delta_text = _message_content_to_input_text(delta.get("content"))
                            if delta_text:
                                text_parts.append(delta_text)
                                yield ResponsesStreamEvent(
                                    event="response.output_text.delta",
                                    type="response.output_text.delta",
                                    response_id=response_id,
                                    response_status="in_progress",
                                    output_text_delta=delta_text,
                                    raw=data,
                                )

                            tool_calls = delta.get("tool_calls") if isinstance(delta.get("tool_calls"), list) else []
                            for tool_call in tool_calls:
                                if not isinstance(tool_call, dict):
                                    continue
                                index = int(tool_call.get("index") or 0)
                                state = tool_state_by_index.setdefault(
                                    index,
                                    {"id": "", "call_id": "", "name": "", "arguments_parts": []},
                                )
                                tool_call_id = str(tool_call.get("id") or "").strip()
                                if tool_call_id:
                                    state["id"] = tool_call_id
                                    state["call_id"] = tool_call_id
                                function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                                function_name = str(function.get("name") or "").strip()
                                if function_name:
                                    state["name"] = function_name
                                argument_piece = str(function.get("arguments") or "")
                                if argument_piece:
                                    state["arguments_parts"].append(argument_piece)

                    final_text = "".join(text_parts).strip()
                    if final_text:
                        yield ResponsesStreamEvent(
                            event="response.output_text.done",
                            type="response.output_text.done",
                            response_id=response_id,
                            response_status=final_status,
                            output_text=final_text,
                            raw={"id": response_id, "status": final_status},
                        )

                    assistant_tool_calls: List[Dict[str, Any]] = []
                    for index in sorted(tool_state_by_index.keys()):
                        state = tool_state_by_index[index]
                        raw_arguments = "".join(state.get("arguments_parts") or []).strip()
                        call_id = str(state.get("call_id") or state.get("id") or f"tool_call_{index}")
                        function_call = ResponsesFunctionCall(
                            id=str(state.get("id") or call_id),
                            call_id=call_id,
                            name=str(state.get("name") or ""),
                            arguments=_parse_tool_arguments(raw_arguments),
                            raw_arguments=raw_arguments,
                        )
                        assistant_tool_calls.append(
                            {
                                "id": function_call.call_id,
                                "type": "function",
                                "function": {
                                    "name": function_call.name,
                                    "arguments": function_call.raw_arguments,
                                },
                            }
                        )
                        yield ResponsesStreamEvent(
                            event="response.function_call_arguments.done",
                            type="response.function_call_arguments.done",
                            response_id=response_id,
                            response_status=final_status,
                            function_call=function_call,
                            item_id=function_call.id,
                            raw={"id": response_id, "status": final_status},
                        )

                    assistant_message: Dict[str, Any] = {"role": "assistant", "content": final_text or None}
                    if assistant_tool_calls:
                        assistant_message["tool_calls"] = assistant_tool_calls
                    self._remember_chat_state(response_id, request_messages, assistant_message)

                    yield ResponsesStreamEvent(
                        event="response.completed",
                        type="response.completed",
                        response_id=response_id,
                        response_status=final_status,
                        output_text=final_text,
                        raw={"id": response_id, "status": final_status},
                    )
                    yield ResponsesStreamEvent(
                        event="response.done",
                        type="response.done",
                        response_id=response_id,
                        response_status=final_status,
                        raw={"done": True},
                    )
                    return
            except HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_error = exc
                if emitted_any or status not in retryable_statuses or attempt >= 2:
                    detail = exc.response.text if exc.response is not None else str(exc)
                    raise RuntimeError(f"assistant_1 chat completions http error {status or 'unknown'}: {detail}") from exc
            except RequestException as exc:
                last_error = exc
                if emitted_any or attempt >= 2:
                    raise RuntimeError(f"assistant_1 chat completions connection error: {exc}") from exc
            time.sleep(0.8 * (attempt + 1))
        if last_error is not None:
            raise RuntimeError(f"assistant_1 chat completions connection error: {last_error}") from last_error

    def _parse_stream_event(
        self,
        *,
        data: Dict[str, Any],
        latest_response_id: str,
        latest_status: str,
        function_calls_by_item_id: Dict[str, ResponsesFunctionCall],
    ) -> ResponsesStreamEvent:
        event_type = str(data.get("type") or "").strip() or "message"
        response_id = latest_response_id
        response_status = latest_status
        if isinstance(data.get("response"), dict):
            response_id = str(data["response"].get("id") or response_id or "")
            response_status = str(data["response"].get("status") or response_status or "")

        output_text_delta = ""
        output_text = ""
        function_call: Optional[ResponsesFunctionCall] = None
        item_id = str(data.get("item_id") or "")

        if event_type == "response.output_text.delta":
            output_text_delta = str(data.get("delta") or "")
        elif event_type == "response.output_text.done":
            output_text = str(data.get("text") or "")
        elif event_type in {"response.output_item.added", "response.output_item.done"}:
            item = data.get("item") if isinstance(data.get("item"), dict) else {}
            item_id = str(item.get("id") or item_id or "")
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "function_call":
                raw_arguments = str(item.get("arguments") or "")
                function_call = ResponsesFunctionCall(
                    id=item_id,
                    call_id=str(item.get("call_id") or ""),
                    name=str(item.get("name") or ""),
                    arguments=_parse_tool_arguments(raw_arguments),
                    raw_arguments=raw_arguments,
                )
                if item_id:
                    function_calls_by_item_id[item_id] = function_call
        elif event_type == "response.function_call_arguments.done":
            item_id = str(data.get("item_id") or "")
            raw_arguments = str(data.get("arguments") or "")
            base_call = function_calls_by_item_id.get(item_id)
            function_call = ResponsesFunctionCall(
                id=item_id or (base_call.id if base_call else ""),
                call_id=base_call.call_id if base_call else "",
                name=base_call.name if base_call else "",
                arguments=_parse_tool_arguments(raw_arguments),
                raw_arguments=raw_arguments,
            )
            if function_call.id:
                function_calls_by_item_id[function_call.id] = function_call

        return ResponsesStreamEvent(
            event=event_type,
            type=event_type,
            response_id=response_id,
            response_status=response_status,
            output_text_delta=output_text_delta,
            output_text=output_text,
            function_call=function_call,
            item_id=item_id,
            raw=data,
        )

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
