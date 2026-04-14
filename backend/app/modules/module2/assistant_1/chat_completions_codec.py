from __future__ import annotations

import json
from typing import Any


def clone_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def normalize_chat_message_list(
    messages: list[dict[str, Any]] | None,
    *,
    instructions: str,
    message_content_to_text,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    instructions_text = str(instructions or "").strip()
    if instructions_text:
        normalized.append({"role": "system", "content": instructions_text})
    for message in messages or []:
        normalized_message = normalize_chat_message(message, message_content_to_text=message_content_to_text)
        if normalized_message is not None:
            normalized.append(normalized_message)
    return normalized


def normalize_chat_message(
    message: dict[str, Any],
    *,
    message_content_to_text,
) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    role = str(message.get("role") or "user").strip().lower() or "user"
    if role == "developer":
        role = "system"
    if role not in {"system", "user", "assistant", "tool"}:
        role = "user"

    content = message.get("content")
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    normalized: dict[str, Any] = {"role": role}

    if role == "tool":
        tool_call_id = str(message.get("tool_call_id") or "").strip()
        text = message_content_to_text(content).strip()
        if not tool_call_id or not text:
            return None
        normalized["tool_call_id"] = tool_call_id
        normalized["content"] = text
        return normalized

    text = message_content_to_text(content).strip()
    if text:
        normalized["content"] = text
    elif role == "assistant" and tool_calls:
        normalized["content"] = None
    else:
        return None

    if role == "assistant" and tool_calls:
        normalized["tool_calls"] = clone_json(tool_calls)
    return normalized


def tool_outputs_to_chat_messages(input_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in input_items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "function_call_output":
            continue
        call_id = str(item.get("call_id") or "").strip()
        if not call_id:
            continue
        output = item.get("output")
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": content,
            }
        )
    return messages


def responses_tools_to_chat_completions(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if str(tool.get("type") or "").strip().lower() != "function":
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": str(tool.get("name") or "").strip(),
                    "description": str(tool.get("description") or "").strip(),
                    "parameters": tool.get("parameters") if isinstance(tool.get("parameters"), dict) else {"type": "object"},
                },
            }
        )
    return converted


def responses_tool_choice_to_chat_completions(tool_choice: str | dict[str, Any]) -> str | dict[str, Any]:
    if isinstance(tool_choice, str):
        choice = tool_choice.strip().lower()
        return choice if choice in {"auto", "none", "required"} else "auto"
    if isinstance(tool_choice, dict) and str(tool_choice.get("type") or "").strip().lower() == "function":
        name = str(tool_choice.get("name") or "").strip()
        if name:
            return {"type": "function", "function": {"name": name}}
    return "auto"


def build_chat_completion_payload(
    *,
    model: str,
    request_messages: list[dict[str, Any]],
    temperature: float,
    max_output_tokens: int,
    tools: list[dict[str, Any]] | None,
    tool_choice: str | dict[str, Any],
    metadata: dict[str, Any] | None,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": request_messages,
        "temperature": temperature,
        "max_tokens": int(max_output_tokens),
    }
    if stream:
        payload["stream"] = True
    chat_tools = responses_tools_to_chat_completions(tools)
    if chat_tools:
        payload["tools"] = chat_tools
        payload["tool_choice"] = responses_tool_choice_to_chat_completions(tool_choice)
    if metadata:
        payload["metadata"] = metadata
    return payload


def parse_chat_completions_response(
    data: dict[str, Any],
    *,
    message_content_to_text,
    parse_tool_arguments,
) -> dict[str, Any]:
    response_id = str(data.get("id") or "")
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    finish_reason = str(choice.get("finish_reason") or "").strip().lower()
    output_text = message_content_to_text(message.get("content")).strip()

    function_calls: list[dict[str, Any]] = []
    assistant_tool_calls: list[dict[str, Any]] = []
    for index, tool_call in enumerate(message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []):
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        raw_arguments = str(function.get("arguments") or "")
        call_id = str(tool_call.get("id") or f"tool_call_{index}")
        function_calls.append(
            {
                "id": call_id,
                "call_id": call_id,
                "name": str(function.get("name") or ""),
                "arguments": parse_tool_arguments(raw_arguments),
                "raw_arguments": raw_arguments,
            }
        )
        assistant_tool_calls.append(clone_json(tool_call))

    assistant_message: dict[str, Any] = {"role": "assistant", "content": output_text or None}
    if assistant_tool_calls:
        assistant_message["tool_calls"] = assistant_tool_calls

    status = "completed" if finish_reason in {"", "stop", "tool_calls"} else "incomplete"
    return {
        "response_id": response_id,
        "status": status,
        "output_text": output_text,
        "function_calls": function_calls,
        "assistant_message": assistant_message,
    }
