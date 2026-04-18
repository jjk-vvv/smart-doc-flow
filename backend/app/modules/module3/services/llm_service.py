from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from .word_processor import get_word_data_url, squish


_RETRYABLE_HTTP_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_MAX_REQUEST_ATTEMPTS = 3
_BASE_RETRY_DELAY_SECONDS = 1.0


def _is_retryable_request_error(exc: requests.exceptions.RequestException) -> bool:
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        return bool(response is not None and response.status_code in _RETRYABLE_HTTP_STATUS_CODES)
    return isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ProxyError,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def _post_json_with_retry(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int = 180,
    max_attempts: int = _MAX_REQUEST_ATTEMPTS,
) -> requests.Response:
    last_error: requests.exceptions.RequestException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt >= max_attempts or not _is_retryable_request_error(exc):
                raise
            backoff_seconds = _BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unexpected request retry failure")


def build_row_template(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}


def build_rows_template(headers: list[str]) -> str:
    template = {"rows": [build_row_template(headers)]}
    return json.dumps(template, ensure_ascii=False, indent=2)


def build_messages(headers: list[str], custom_prompt: str, doc_text: str, image_count: int) -> tuple[str, str]:
    header_text = ", ".join(headers)
    rows_template = build_rows_template(headers)
    system_prompt = (
        "You are a rigorous structured-data extraction engine. "
        "Extract data from the provided Word content and return only a JSON object that can be parsed by json.loads. "
        'The top-level object must contain a "rows" field whose value is an array. '
        "Each item in rows represents one record. "
        "The keys of every row must exactly match the provided target headers. "
        "Do not add extra keys and do not omit required keys. "
        "If a value cannot be determined, use an empty string. "
        "Preserve factual values from the source whenever possible. "
        "If you need to normalize or generate explanatory free-text content, write it in Simplified Chinese."
    )
    user_prompt = (
        f"[Target Headers]\n{header_text}\n\n"
        f"[User Requirements]\n{custom_prompt}\n\n"
        "[Output Rules]\n"
        "1) Return a JSON object only. Do not return Markdown or explanations.\n"
        '2) The top-level format must be {"rows": [...]}.\n'
        "3) The key of each object in rows must exactly match the target headers.\n"
        "4) Keep values concise, readable, and suitable for downstream storage.\n"
        "5) The output must be strict JSON using double quotes only, with no trailing commas and no comments.\n"
        "6) Normalize dates to YYYY-MM-DD when possible. Normalize numeric amounts to Arabic numerals when possible.\n"
        "7) If the document contains multiple records, split them into multiple rows.\n"
        "8) Keep factual values from the source. If you need to summarize or normalize descriptive text, use Simplified Chinese.\n\n"
        f"[JSON Output Template]\n{rows_template}\n\n"
        f"[Parsed Word Text]\n{doc_text}\n\n"
        f"[Image Inputs]\nThis request may also include {image_count} images extracted from embedded Word images, "
        "possibly with figure or table captions. Use both the images and the captions together when extracting data."
    )
    return system_prompt, user_prompt


def build_repair_messages(headers: list[str], bad_output: str) -> tuple[str, str]:
    rows_template = build_rows_template(headers)
    system_prompt = (
        "You are a JSON repair assistant. "
        "Return only one JSON object that can be parsed by json.loads, with no explanations."
    )
    user_prompt = (
        "Repair the content below into strict JSON.\n"
        "Requirements:\n"
        '1) The top-level object must be {"rows": [...]}.\n'
        "2) Keep only the target fields. Do not add fields and do not omit required fields.\n"
        "3) Every object in rows must use keys that exactly match the target headers.\n"
        "4) If a value cannot be determined, use an empty string.\n"
        "5) If you need to normalize or generate descriptive free-text content, write it in Simplified Chinese.\n\n"
        f"[Target Headers]\n{', '.join(headers)}\n\n"
        f"[JSON Output Template]\n{rows_template}\n\n"
        f"[Content To Repair]\n{bad_output}"
    )
    return system_prompt, user_prompt


def build_excel_source_messages(headers: list[str], custom_prompt: str, excel_text: str) -> tuple[str, str]:
    system_prompt = (
        "You are a rigorous structured-data extraction engine. "
        "Extract fields from the provided Excel row text and return only a JSON object that can be parsed by json.loads. "
        'The top-level object must contain a "rows" field whose value is an array. '
        "Each item in rows represents one record. "
        "The keys of every row must exactly match the provided target headers. "
        "Do not add extra keys and do not omit required keys. "
        "If a value cannot be determined, use an empty string. "
        "If the user requirements ask for filtering, normalization, or regrouping, follow those requirements first. "
        "If there is no extra filtering requirement, keep as many valid rows as possible. "
        "If you need to normalize or generate explanatory free-text content, write it in Simplified Chinese."
    )
    user_prompt = (
        f"[Target Headers]\n{', '.join(headers)}\n\n"
        f"[User Requirements]\n{custom_prompt}\n\n"
        f"[Parsed Excel Text]\n{excel_text}\n\n"
        "[Output Rules]\n"
        "1) Return a JSON object only. Do not return Markdown or explanations.\n"
        '2) The top-level format must be {"rows": [...]}.\n'
        "3) The key of each object in rows must exactly match the target headers.\n"
        "4) The output must be strict JSON using double quotes only, with no trailing commas and no comments.\n"
        "5) If the text contains multiple records, split them into multiple rows.\n"
        "6) Keep factual values from the source. If you need to summarize or normalize descriptive text, use Simplified Chinese.\n"
    )
    return system_prompt, user_prompt


def request_text_responses(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
    }

    resp = _post_json_with_retry(
        f"{base_url}/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()

    texts: list[str] = []
    for item in data.get("output", []):
        for content_item in item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if isinstance(content_item.get("text"), str) and content_item["text"].strip():
                texts.append(content_item["text"].strip())
            elif isinstance(content_item.get("text"), dict):
                value = content_item["text"].get("value")
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())

    if texts:
        return "\n".join(texts)

    raise ValueError(f"responses 接口返回中未找到文本输出: {json.dumps(data, ensure_ascii=False)[:600]}")


def request_responses(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    word_path: Path,
    include_file: bool,
    image_inputs: list[dict[str, str]] | None = None,
) -> str:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]

    for idx, image in enumerate(image_inputs or [], start=1):
        caption = squish(str(image.get("caption", "")))
        if caption:
            content.append({"type": "input_text", "text": f"Image {idx} caption/context: {caption}"})
        content.append({"type": "input_image", "image_url": image["data_url"]})

    if include_file:
        mime, b64_data = get_word_data_url(word_path)
        content.append(
            {
                "type": "input_file",
                "filename": word_path.name,
                "file_data": f"data:{mime};base64,{b64_data}",
            }
        )

    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": content,
            },
        ],
    }

    resp = _post_json_with_retry(
        f"{base_url}/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()

    texts: list[str] = []
    for item in data.get("output", []):
        for content_item in item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            if isinstance(content_item.get("text"), str) and content_item["text"].strip():
                texts.append(content_item["text"].strip())
            elif isinstance(content_item.get("text"), dict):
                value = content_item["text"].get("value")
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())

    if texts:
        return "\n".join(texts)

    raise ValueError(f"responses 接口返回中未找到文本输出: {json.dumps(data, ensure_ascii=False)[:600]}")


def request_chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_inputs: list[dict[str, str]] | None = None,
) -> str:
    user_content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for idx, image in enumerate(image_inputs or [], start=1):
        caption = squish(str(image.get("caption", "")))
        if caption:
            user_content.append({"type": "text", "text": f"Image {idx} caption/context: {caption}"})
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": image["data_url"]},
            }
        )

    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    resp = _post_json_with_retry(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"chat/completions 返回异常: {json.dumps(data, ensure_ascii=False)[:600]}")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()

    raise ValueError(f"无法解析 chat/completions 的输出: {json.dumps(data, ensure_ascii=False)[:600]}")


def find_first_json_value(text: str) -> str:
    start = -1
    for idx, ch in enumerate(text):
        if ch in "{[":
            start = idx
            break
    if start == -1:
        raise ValueError("模型输出中未找到 JSON")

    stack: list[str] = []
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                raise ValueError("模型输出中的 JSON 结构不完整")
            opener = stack[-1]
            if (opener == "{" and ch == "}") or (opener == "[" and ch == "]"):
                stack.pop()
            else:
                raise ValueError("模型输出中的 JSON 括号不匹配")
            if not stack:
                return text[start : idx + 1]

    raise ValueError("模型输出中的 JSON 结构不完整")


def parse_model_json(raw_text: str) -> Any:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        json_text = find_first_json_value(raw_text)
        data = json.loads(json_text)
    return data


def normalize_output(headers: list[str], raw_data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for header in headers:
        value = raw_data.get(header, "")
        if value is None:
            out[header] = ""
        elif isinstance(value, (dict, list)):
            out[header] = json.dumps(value, ensure_ascii=False)
        else:
            out[header] = str(value).strip()
    return out


def to_rows_data(parsed_data: Any) -> list[dict[str, Any]]:
    if isinstance(parsed_data, list):
        rows = parsed_data
    elif isinstance(parsed_data, dict):
        rows = None
        for key in ("rows", "data", "records", "items", "list", "result"):
            value = parsed_data.get(key)
            if isinstance(value, list):
                rows = value
                break
        if rows is None:
            rows = [parsed_data]
    else:
        raise ValueError("模型输出不是对象或数组，无法映射为表格行")

    dict_rows = [item for item in rows if isinstance(item, dict)]
    if not dict_rows:
        raise ValueError("模型输出中没有有效的对象行数据")
    return dict_rows


def normalize_rows_output(headers: list[str], parsed_data: Any) -> list[dict[str, str]]:
    rows = to_rows_data(parsed_data)
    return [normalize_output(headers, row) for row in rows]


__all__ = [
    "build_excel_source_messages",
    "build_messages",
    "build_repair_messages",
    "build_row_template",
    "build_rows_template",
    "find_first_json_value",
    "normalize_output",
    "normalize_rows_output",
    "parse_model_json",
    "request_chat_completions",
    "request_responses",
    "request_text_responses",
    "to_rows_data",
]
