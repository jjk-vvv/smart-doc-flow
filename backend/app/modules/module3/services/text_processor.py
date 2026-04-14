from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .llm_service import (
    find_first_json_value as _find_first_json_value,
    normalize_output as _normalize_output,
    normalize_rows_output as _normalize_rows_output,
    parse_model_json as _parse_model_json,
    request_text_responses as _request_text_responses,
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


def read_txt_source_content(source_path: Path) -> str:
    text = read_text_file(source_path)
    return text.strip()


def try_parse_kv(txt_text: str, headers: list[str]) -> list[dict[str, str]] | None:
    lines = txt_text.split("\n")

    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in lines:
        if ":" not in line and "：" not in line:
            continue
        parts = re.split(r":|：", line, maxsplit=1)
        if len(parts) != 2:
            continue

        key = parts[0].strip()
        value = parts[1].strip()
        if key in headers:
            current[key] = value

        if len(current) == len(headers):
            rows.append(current)
            current = {}

    return rows if rows else None


def build_txt_messages(
    headers: list[str],
    txt_text: str,
    custom_prompt: str,
    candidate_text: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are a high-precision structured-data extraction engine.\n"
        "Your task is to extract structured data from TXT content.\n\n"
        "You must follow these rules:\n"
        "1. Output JSON only.\n"
        '2. The top-level structure must be {"rows": [...]}.\n'
        "3. Each row represents one record.\n"
        "4. Field keys must exactly match the provided headers.\n"
        "5. Do not add new fields.\n"
        '6. If a value cannot be found, use "".\n'
        "7. Do not invent facts.\n"
        "8. Cover as much valid data as possible.\n"
        "9. If you need to normalize or generate descriptive free-text content, write it in Simplified Chinese.\n"
    )

    image_count = 0
    user_prompt = (
        f"[Target Headers]\n{', '.join(headers)}\n\n"
        f"[User Requirements]\n{custom_prompt}\n\n"
        f"[Candidate Result]\n{candidate_text}\n\n"
        f"[TXT Content]\n{txt_text}\n\n"
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
        f"[TXT Content]\n{doc_text}\n\n"
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


def request_text_responses(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    return _request_text_responses(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


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


def extract_rows_from_txt_source(
    txt_path: Path,
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
    if normalized_mode not in {"responses", "chat"}:
        raise ValueError("api_mode 只支持 responses 或 chat")

    log_event(logger, f"[步骤1] 已读取 TXT 数据文件: {txt_path.name}")
    txt_text = read_txt_source_content(txt_path)

    candidate_rows = try_parse_kv(txt_text, headers)
    candidate_text = ""
    if candidate_rows:
        candidate_text = json.dumps({"rows": candidate_rows}, ensure_ascii=False, indent=2)
        log_event(logger, "[优化] 命中 key:value 候选解析，继续按用户要求核验。")

    system_prompt, user_prompt = build_txt_messages(headers, txt_text, prompt, candidate_text)
    log_event(logger, f"[步骤1.1] 已读取表头，共 {len(headers)} 个字段。")
    log_event(logger, "[步骤2] 开始调用模型进行数据抽取。")

    if normalized_mode == "responses":
        try:
            log_event(logger, "[模型调用] /v1/responses（纯文本）")
            model_text = request_text_responses(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            log_event(logger, f"[模型调用回退] responses 失败，改用 chat。原因: {exc}")
            model_text = request_chat_completions(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
    else:
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
        if normalized_mode == "responses":
            try:
                log_event(logger, "[模型调用] JSON 修复：/v1/responses")
                repair_text = request_text_responses(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    system_prompt=repair_system_prompt,
                    user_prompt=repair_user_prompt,
                )
            except Exception as exc2:
                log_event(logger, f"[模型调用回退] responses 修复失败，改用 chat。原因: {exc2}")
                repair_text = request_chat_completions(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    system_prompt=repair_system_prompt,
                    user_prompt=repair_user_prompt,
                )
        else:
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
