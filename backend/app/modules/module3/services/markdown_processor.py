from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .llm_service import (
    find_first_json_value as _find_first_json_value,
    normalize_output as _normalize_output,
    normalize_rows_output as _normalize_rows_output,
    parse_model_json as _parse_model_json,
    to_rows_data as _to_rows_data,
)
from .text_source_common import (
    log_event as _log_event,
    read_text_file as _read_text_file,
    request_chat_completions as _request_chat_completions,
)


def log_event(logger: Callable[[str], None] | None, message: str) -> None:
    _log_event(logger, message)


def read_text_file(path: Path) -> str:
    return _read_text_file(path)


def read_markdown_source_content(source_path: Path) -> str:
    text = read_text_file(source_path)
    return text.strip()


def try_parse_markdown_table(markdown_text: str, headers: list[str]) -> list[dict[str, str]] | None:
    lines = markdown_text.split("\n")

    table: list[list[str]] = []
    for line in lines:
        if "|" not in line:
            continue
        parts = [chunk.strip() for chunk in line.split("|") if chunk.strip()]
        if parts:
            table.append(parts)

    if len(table) < 2:
        return None

    md_headers = table[0]
    rows: list[dict[str, str]] = []
    for row in table[2:]:
        item: dict[str, str] = {}
        for header in headers:
            if header in md_headers:
                idx = md_headers.index(header)
                item[header] = row[idx] if idx < len(row) else ""
            else:
                item[header] = ""
        rows.append(item)

    return rows if rows else None


def build_messages(
    headers: list[str],
    markdown_text: str,
    custom_prompt: str,
    candidate_text: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are a high-precision structured-data extraction engine.\n"
        "Your task is to extract structured data from Markdown text and return strict JSON.\n\n"
        "You must follow these rules:\n"
        "1. Output JSON only, with no explanations.\n"
        '2. The top-level structure must be {"rows": [...]}.\n'
        "3. Each row represents one record.\n"
        "4. Every field key must exactly match the provided headers.\n"
        "5. Do not add fields and do not omit required fields.\n"
        '6. If a value cannot be found, use "".\n'
        "7. Do not invent facts.\n"
        "8. Tables, lists, and paragraphs in Markdown may all contain useful data.\n"
        "9. If there are multiple records, split them into multiple rows.\n"
        "10. If you need to normalize or generate descriptive free-text content, write it in Simplified Chinese.\n"
    )

    image_count = 0
    user_prompt = (
        f"[Target Headers]\n{', '.join(headers)}\n\n"
        f"[User Requirements]\n{custom_prompt}\n\n"
        f"[Candidate Result]\n{candidate_text}\n\n"
        f"[Markdown Content]\n{markdown_text}\n\n"
        f"[Image Inputs]\nThis request includes {image_count} images.\n"
        "[Validation Requirements]\n"
        "1) Return a top-level JSON object that contains rows and field_audits.\n"
        "2) rows must be the final result after your validation.\n"
        "3) field_audits must provide field-level validation details.\n"
        "4) status may only be pass, fixed, or low_confidence.\n"
        "5) confidence must be between 0 and 1.\n"
        "6) Any explanatory text inside field_audits must be written in Simplified Chinese.\n"
    )
    return system_prompt, user_prompt


def build_repair_messages(headers: list[str], bad_output: str) -> tuple[str, str]:
    system_prompt = (
        "You are a JSON repair assistant. "
        "Return only one JSON object that can be parsed by json.loads, with no explanations."
    )
    custom_prompt = ""
    doc_text = ""
    image_count = 0
    user_prompt = (
        f"[Target Headers]\n{', '.join(headers)}\n\n"
        f"[User Requirements]\n{custom_prompt}\n\n"
        f"[Candidate Result]\n{bad_output}\n\n"
        f"[Markdown Content]\n{doc_text}\n\n"
        f"[Image Inputs]\nThis request includes {image_count} images.\n"
        "[Validation Requirements]\n"
        "1) Return a top-level JSON object that contains rows and field_audits.\n"
        "2) rows must be the final result after your validation.\n"
        "3) field_audits must provide field-level validation details.\n"
        "4) status may only be pass, fixed, or low_confidence.\n"
        "5) confidence must be between 0 and 1.\n"
        "6) Any explanatory text inside field_audits must be written in Simplified Chinese.\n"
    )
    return system_prompt, user_prompt




def request_chat_completions(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    return _request_chat_completions(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def find_first_json_value(text: str) -> str:
    return _find_first_json_value(text)


def parse_model_json(raw_text: str) -> Any:
    return _parse_model_json(raw_text)


def normalize_output(headers: list[str], raw_data: dict[str, Any]) -> dict[str, str]:
    return _normalize_output(headers, raw_data)


def to_rows_data(parsed_data: Any) -> list[dict[str, Any]]:
    return _to_rows_data(parsed_data)


def normalize_rows_output(headers: list[str], parsed_data: Any) -> list[dict[str, str]]:
    return _normalize_rows_output(headers, parsed_data)


def extract_rows_from_markdown_source(
    markdown_path: Path,
    headers: list[str],
    prompt: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    api_mode: str,
    logger: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    normalized_mode = api_mode.strip().lower()
    if normalized_mode != "chat":
        raise ValueError("api_mode 只支持 chat")

    log_event(logger, f"[步骤1] 已读取 Markdown 数据文件: {markdown_path.name}")
    markdown_text = read_markdown_source_content(markdown_path)

    candidate_rows = try_parse_markdown_table(markdown_text, headers)
    candidate_text = ""
    if candidate_rows:
        candidate_text = json.dumps({"rows": candidate_rows}, ensure_ascii=False, indent=2)
        log_event(logger, "[优化] 命中 Markdown 表格候选解析，继续按用户要求核验。")

    system_prompt, user_prompt = build_messages(headers, markdown_text, prompt, candidate_text)
    log_event(logger, f"[步骤1.1] 已读取表头，共 {len(headers)} 个字段。")
    log_event(logger, "[步骤2] 开始调用模型进行数据抽取。")

    if normalized_mode != "chat":
        raise ValueError("Module 3 only supports chat API mode.")
    log_event(logger, "[模型调用] /v1/chat/completions（纯文本）")
    model_text = request_chat_completions(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    log_event(logger, "[模型输出-抽取]\n" + model_text)

    try:
        parsed_data = parse_model_json(model_text)
    except Exception as exc:
        log_event(logger, f"[解析失败] 首次输出不是可用 JSON，开始修复。原因: {exc}")
        repair_system_prompt, repair_user_prompt = build_repair_messages(headers, model_text)
        if normalized_mode != "chat":
            raise ValueError("Module 3 only supports chat API mode.")
        log_event(logger, "[模型调用] JSON 修复：/v1/chat/completions")
        repair_text = request_chat_completions(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=repair_system_prompt,
            user_prompt=repair_user_prompt,
        )
        log_event(logger, "[模型输出-修复]\n" + repair_text)
        parsed_data = parse_model_json(repair_text)

    rows_values = normalize_rows_output(headers, parsed_data)
    log_event(logger, f"[步骤3] 解析完成，共 {len(rows_values)} 行。")
    log_event(logger, "[解析后的标准化结果]\n" + json.dumps({"rows": rows_values}, ensure_ascii=False, indent=2))
    return rows_values
