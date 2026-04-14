from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Callable

from ..core.config import DEFAULT_PROMPT
from .llm_service import parse_model_json, request_chat_completions, request_text_responses
from .source_dispatcher import simple_match_excel_headers
from .text_source_common import log_event


_ALLOWED_OPERATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "not_empty",
    "empty",
}

_OPERATOR_ALIASES = {
    "等于": "eq",
    "是": "eq",
    "=": "eq",
    "不等于": "neq",
    "不是": "neq",
    "包含": "contains",
    "不包含": "not_contains",
    "大于": "gt",
    "大于等于": "gte",
    "不小于": "gte",
    "小于": "lt",
    "小于等于": "lte",
    "不大于": "lte",
    "属于": "in",
    "在其中": "in",
    "不属于": "not_in",
    "非空": "not_empty",
    "为空": "empty",
}


def has_effective_user_prompt(user_prompt: str) -> bool:
    prompt = (user_prompt or "").strip()
    default_prompt = DEFAULT_PROMPT.strip()
    return bool(prompt) and prompt != default_prompt


def _normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).strip()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[\W_]+", "", _normalize_text(value).lower(), flags=re.UNICODE)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _normalize_text(value).lower()
    return text in {"true", "1", "yes", "是", "有"}


def _pick_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [value]
    else:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _normalize_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _dedupe_headers(*header_groups: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in header_groups:
        for item in group:
            text = _normalize_text(item)
            if not text:
                continue
            key = _normalize_key(text)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(text)
    return ordered


def _build_sample_rows(rows: list[dict[str, str]], *, limit_rows: int = 5, limit_fields: int = 12) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for row in rows[:limit_rows]:
        sample: dict[str, str] = {}
        count = 0
        for key, value in row.items():
            text_key = _normalize_text(key)
            text_value = _normalize_text(value)
            if not text_key or not text_value:
                continue
            sample[text_key] = text_value
            count += 1
            if count >= limit_fields:
                break
        if sample:
            payload.append(sample)
    return payload


def _build_field_value_examples(
    rows: list[dict[str, str]],
    *,
    max_fields: int = 20,
    max_values_per_field: int = 6,
    scan_rows: int = 300,
) -> dict[str, list[str]]:
    examples: dict[str, list[str]] = {}
    seen_by_field: dict[str, set[str]] = {}

    for row in rows[:scan_rows]:
        for key, value in row.items():
            field = _normalize_text(key)
            text = _normalize_text(value)
            if not field or not text:
                continue
            if field not in examples and len(examples) >= max_fields:
                continue
            examples.setdefault(field, [])
            seen_by_field.setdefault(field, set())
            if text in seen_by_field[field]:
                continue
            if len(examples[field]) >= max_values_per_field:
                continue
            seen_by_field[field].add(text)
            examples[field].append(text)

    return {field: values for field, values in examples.items() if values}


def _build_requirement_understanding_messages(
    user_prompt: str,
    *,
    template_filename: str = "",
    scopes: list[dict[str, Any]] | None = None,
    target_headers: list[str] | None = None,
    context_text: str = "",
) -> tuple[str, str]:
    system_prompt = (
        "You are responsible for first understanding the user's natural-language form-filling requirements. "
        "Perform intent understanding first; do not directly generate field-level filtering rules. "
        "Rewrite the user's original request into a clearer, executable, and dispatchable requirement summary. "
        "Return valid JSON only, with no explanations."
    )
    user_prompt_text = (
        f"[Original User Request]\n{user_prompt}\n\n"
        f"[Template Filename]\n{template_filename}\n\n"
        f"[Current Target Fields]\n{json.dumps(target_headers or [], ensure_ascii=False)}\n\n"
        f"[Current Context Notes]\n{context_text}\n\n"
        f"[Available Scopes]\n{json.dumps(scopes or [], ensure_ascii=False)}\n\n"
        "Return only the following JSON structure:\n"
        "{\n"
        '  "ignore": false,\n'
        '  "ignore_reason": "",\n'
        '  "task_goal": "",\n'
        '  "global_requirements": ["..."],\n'
        '  "local_requirements": ["..."],\n'
        '  "sort_requirements": ["..."],\n'
        '  "limit_requirements": ["..."],\n'
        '  "dedupe_requirements": ["..."],\n'
        '  "output_requirements": ["..."],\n'
        '  "notes": ["..."]\n'
        "}\n\n"
        "Rules:\n"
        "1) First understand what the user wants, then rewrite it as concise requirements.\n"
        "2) Keep only constraints that truly apply to the entire task under global_requirements.\n"
        "3) Put constraints that clearly apply only to one table, one data subset, or one part of the result under local_requirements.\n"
        "4) Organize sorting, quantity, deduplication, and output restrictions separately; do not mix them with filtering constraints.\n"
        "5) Do not invent facts that do not exist in the template, fields, or source files.\n"
        "6) If the user request is empty, invalid, irrelevant, or not executable, you may return ignore=true.\n"
    )
    return system_prompt, user_prompt_text


def _sanitize_requirement_understanding(raw_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "ignore": _as_bool(_pick_value(raw_plan, "忽略", "ignore")),
        "ignore_reason": _normalize_text(_pick_value(raw_plan, "忽略原因", "ignore_reason")),
        "task_goal": _normalize_text(_pick_value(raw_plan, "任务目标", "task_goal")),
        "global_requirements": _as_string_list(_pick_value(raw_plan, "全局要求", "global_requirements")),
        "local_requirements": _as_string_list(_pick_value(raw_plan, "局部要求", "local_requirements")),
        "sort_requirements": _as_string_list(_pick_value(raw_plan, "排序要求", "sort_requirements")),
        "limit_requirements": _as_string_list(_pick_value(raw_plan, "数量要求", "limit_requirements")),
        "dedupe_requirements": _as_string_list(_pick_value(raw_plan, "去重要求", "dedupe_requirements")),
        "output_requirements": _as_string_list(_pick_value(raw_plan, "输出要求", "output_requirements")),
        "notes": _as_string_list(_pick_value(raw_plan, "备注", "notes")),
    }


def _compose_understood_prompt(understanding: dict[str, Any], fallback_prompt: str) -> str:
    if understanding.get("ignore"):
        return fallback_prompt

    parts: list[str] = []
    task_goal = _normalize_text(understanding.get("task_goal"))
    if task_goal:
        parts.append("[Task Goal]\n" + task_goal)

    section_map = [
        ("Global Requirements", understanding.get("global_requirements", [])),
        ("Local Requirements", understanding.get("local_requirements", [])),
        ("Sort Requirements", understanding.get("sort_requirements", [])),
        ("Limit Requirements", understanding.get("limit_requirements", [])),
        ("Dedupe Requirements", understanding.get("dedupe_requirements", [])),
        ("Output Requirements", understanding.get("output_requirements", [])),
        ("Notes", understanding.get("notes", [])),
    ]
    for title, items in section_map:
        values = _as_string_list(items)
        if values:
            parts.append(f"[{title}]\n" + "\n".join(f"- {item}" for item in values))

    return "\n\n".join(parts) if parts else fallback_prompt


def _is_prepared_requirement_prompt(user_prompt: str) -> bool:
    prompt = user_prompt or ""
    markers = (
        "[Task Goal]",
        "[Global Requirements]",
        "[Local Requirements]",
        "[Current Scope Requirements]",
        "[任务目标]",
        "[全局要求]",
        "[局部要求]",
        "[当前作用域要求]",
    )
    return any(marker in prompt for marker in markers)


def _request_rule_plan(
    *,
    settings: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    if settings["api_mode"] == "responses":
        try:
            raw_text = request_text_responses(
                base_url=settings["base_url"],
                api_key=settings["api_key"],
                model=settings["model"],
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception:
            raw_text = request_chat_completions(
                base_url=settings["base_url"],
                api_key=settings["api_key"],
                model=settings["model"],
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_inputs=None,
            )
    else:
        raw_text = request_chat_completions(
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            model=settings["model"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_inputs=None,
        )
    parsed = parse_model_json(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("用户要求规划器没有返回 JSON 对象")
    return parsed


def _resolve_requirement_understanding(
    *,
    user_prompt: str,
    settings: dict[str, Any],
    logger: Callable[[str], None] | None = None,
    template_filename: str = "",
    scopes: list[dict[str, Any]] | None = None,
    target_headers: list[str] | None = None,
    context_text: str = "",
) -> dict[str, Any]:
    raw_prompt = (user_prompt or "").strip()
    if not has_effective_user_prompt(raw_prompt):
        return {
            "ignore": True,
            "ignore_reason": "empty or default prompt",
            "task_goal": "",
            "global_requirements": [],
            "local_requirements": [],
            "sort_requirements": [],
            "limit_requirements": [],
            "dedupe_requirements": [],
            "output_requirements": [],
            "notes": [],
        }
    if _is_prepared_requirement_prompt(raw_prompt):
        return {
            "ignore": False,
            "ignore_reason": "",
            "task_goal": "",
            "global_requirements": [],
            "local_requirements": [],
            "sort_requirements": [],
            "limit_requirements": [],
            "dedupe_requirements": [],
            "output_requirements": [],
            "notes": [],
        }

    system_prompt, user_prompt_text = _build_requirement_understanding_messages(
        raw_prompt,
        template_filename=template_filename,
        scopes=scopes,
        target_headers=target_headers,
        context_text=context_text,
    )
    raw_plan = _request_rule_plan(
        settings=settings,
        system_prompt=system_prompt,
        user_prompt=user_prompt_text,
    )
    understanding = _sanitize_requirement_understanding(raw_plan)
    if understanding.get("ignore"):
        if not understanding.get("ignore_reason"):
            understanding["ignore_reason"] = "understanding ignored"
        return understanding

    summary = {
        "任务目标": understanding["task_goal"],
        "全局要求": understanding["global_requirements"],
        "局部要求": understanding["local_requirements"],
        "排序要求": understanding["sort_requirements"],
        "数量要求": understanding["limit_requirements"],
        "去重要求": understanding["dedupe_requirements"],
        "输出要求": understanding["output_requirements"],
    }
    log_event(logger, "[user rules] 理解结果: " + json.dumps(summary, ensure_ascii=False))
    return understanding


def _build_scope_assignment_messages(
    user_prompt: str,
    scopes: list[dict[str, Any]],
    *,
    template_filename: str = "",
    understanding: dict[str, Any] | None = None,
) -> tuple[str, str]:
    system_prompt = (
        "You are responsible for assigning user requirements to the correct template scopes. "
        "Do not incorrectly elevate a scope-specific constraint into a global requirement. "
        "Return valid JSON only, with no explanations."
    )
    user_prompt_text = (
        f"[Original User Request]\n{user_prompt}\n\n"
        f"[Requirement Understanding]\n{json.dumps(understanding or {}, ensure_ascii=False)}\n\n"
        f"[Template Filename]\n{template_filename}\n\n"
        f"[Scope List]\n{json.dumps(scopes, ensure_ascii=False)}\n\n"
        "Return only the following JSON structure:\n"
        "{\n"
        '  "global_requirements": ["..."],\n'
        '  "scopes": [\n'
        '    {"scope_id": "an existing scope ID from the input", "requirements": ["..."]}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "1) You may use only scope IDs that already exist in the input.\n"
        "2) If a requirement clearly belongs to only one scope, place it only in that scope.\n"
        "3) Only requirements that truly apply to every scope may be placed in global_requirements.\n"
        "4) Preserve concrete constraints such as time, region, category, range, sorting, and quantity.\n"
        "5) Do not invent new scopes, fields, or facts.\n"
    )
    return system_prompt, user_prompt_text


def _sanitize_scope_assignment(
    raw_plan: dict[str, Any],
    scope_ids: list[str],
) -> dict[str, Any]:
    valid_scope_ids = {_normalize_text(scope_id) for scope_id in scope_ids if _normalize_text(scope_id)}
    global_requirements = _as_string_list(_pick_value(raw_plan, "全局要求", "global_requirements"))

    scope_requirements: dict[str, list[str]] = {scope_id: [] for scope_id in scope_ids}
    raw_scopes = _pick_value(raw_plan, "作用域", "scopes")
    if isinstance(raw_scopes, list):
        for item in raw_scopes:
            if not isinstance(item, dict):
                continue
            scope_id = _normalize_text(_pick_value(item, "作用域ID", "scope_id"))
            if not scope_id or scope_id not in valid_scope_ids:
                continue
            scope_requirements[scope_id] = _as_string_list(_pick_value(item, "要求", "requirements"))

    return {
        "global_requirements": global_requirements,
        "scope_requirements": scope_requirements,
    }


def _compose_scoped_prompt(
    understanding: dict[str, Any],
    global_requirements: list[str],
    scope_requirements: list[str],
    fallback_prompt: str,
) -> str:
    if not global_requirements and not scope_requirements:
        return _compose_understood_prompt(understanding, fallback_prompt)

    parts: list[str] = []
    task_goal = _normalize_text(understanding.get("task_goal"))
    if task_goal:
        parts.append("[Task Goal]\n" + task_goal)
    if global_requirements:
        parts.append("[Global Requirements]\n" + "\n".join(f"- {item}" for item in global_requirements))
    if scope_requirements:
        parts.append("[Current Scope Requirements]\n" + "\n".join(f"- {item}" for item in scope_requirements))

    section_map = [
        ("Sort Requirements", understanding.get("sort_requirements", [])),
        ("Limit Requirements", understanding.get("limit_requirements", [])),
        ("Dedupe Requirements", understanding.get("dedupe_requirements", [])),
        ("Output Requirements", understanding.get("output_requirements", [])),
        ("Notes", understanding.get("notes", [])),
    ]
    for title, items in section_map:
        values = _as_string_list(items)
        if values:
            parts.append(f"[{title}]\n" + "\n".join(f"- {item}" for item in values))

    return "\n\n".join(parts) if parts else fallback_prompt


def resolve_scope_user_prompts(
    *,
    user_prompt: str,
    scopes: list[dict[str, Any]],
    settings: dict[str, Any],
    logger: Callable[[str], None] | None = None,
    template_filename: str = "",
) -> dict[str, str]:
    raw_prompt = (user_prompt or "").strip()
    scope_ids = [str(scope.get("scope_id", "")).strip() for scope in scopes if str(scope.get("scope_id", "")).strip()]
    fallback = {scope_id: raw_prompt for scope_id in scope_ids}

    if not has_effective_user_prompt(raw_prompt):
        return fallback
    if len(scope_ids) <= 1:
        return fallback

    try:
        understanding = _resolve_requirement_understanding(
            user_prompt=raw_prompt,
            settings=settings,
            logger=logger,
            template_filename=template_filename,
            scopes=scopes,
        )
    except Exception as exc:
        log_event(logger, f"[user rules] 理解阶段回退: {exc}")
        understanding = {
            "ignore": False,
            "ignore_reason": "",
            "task_goal": "",
            "global_requirements": [],
            "local_requirements": [],
            "sort_requirements": [],
            "limit_requirements": [],
            "dedupe_requirements": [],
            "output_requirements": [],
            "notes": [],
        }

    system_prompt, user_prompt_text = _build_scope_assignment_messages(
        raw_prompt,
        scopes,
        template_filename=template_filename,
        understanding=understanding,
    )

    try:
        raw_plan = _request_rule_plan(
            settings=settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt_text,
        )
    except Exception as exc:
        log_event(logger, f"[user rules] 作用域分配回退: {exc}")
        return fallback

    assignment = _sanitize_scope_assignment(raw_plan, scope_ids)
    prompts = {
        scope_id: _compose_scoped_prompt(
            understanding,
            assignment["global_requirements"],
            assignment["scope_requirements"].get(scope_id, []),
            raw_prompt,
        )
        for scope_id in scope_ids
    }

    log_event(
        logger,
        "[user rules] 作用域要求: "
        + json.dumps(
            {
                "全局要求": assignment["global_requirements"],
                "作用域要求": assignment["scope_requirements"],
            },
            ensure_ascii=False,
        ),
    )
    return prompts


def _build_rule_plan_messages(
    user_prompt: str,
    target_headers: list[str],
    *,
    available_headers: list[str] | None = None,
    context_text: str = "",
    template_filename: str = "",
    source_context_text: str = "",
    sample_rows: list[dict[str, str]] | None = None,
    field_value_examples: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    system_prompt = (
        "You are responsible for converting the already-organized user requirements into executable field rules. "
        "Use the template fields, available fields, sample rows, field value examples, and context to decide. "
        "Return valid JSON only, with no explanations."
    )
    user_prompt_text = (
        f"[Organized User Requirements]\n{user_prompt}\n\n"
        f"[Target Fields]\n{json.dumps(target_headers, ensure_ascii=False)}\n\n"
        f"[Available Fields]\n{json.dumps(available_headers or target_headers, ensure_ascii=False)}\n\n"
        f"[Template Filename]\n{template_filename}\n\n"
        f"[Template Context]\n{context_text}\n\n"
        f"[Source Data Context]\n{source_context_text}\n\n"
        f"[Sample Rows]\n{json.dumps(sample_rows or [], ensure_ascii=False)}\n\n"
        f"[Field Value Examples]\n{json.dumps(field_value_examples or {}, ensure_ascii=False)}\n\n"
        "Return only the following JSON structure:\n"
        "{\n"
        '  "ignore": false,\n'
        '  "ignore_reason": "",\n'
        '  "standardized_requirements": ["..."],\n'
        '  "field_requirements": [\n'
        '    {"field": "one field from Available Fields", "operator": "eq", "value": "some value", "values": []}\n'
        "  ],\n"
        '  "sort": [{"field": "one field from Available Fields", "direction": "asc"}],\n'
        '  "row_limit": null,\n'
        '  "dedupe_by": ["one field from Available Fields"]\n'
        "}\n\n"
        "Rules:\n"
        "1) standardized_requirements should restate the user's real intent as short, clear, executable statements.\n"
        "2) field_requirements should describe only how to filter row data; do not describe the act of filling the form itself.\n"
        "3) operator may only be one of eq, neq, contains, not_contains, gt, gte, lt, lte, in, not_in, not_empty, empty.\n"
        "4) Prefer fields from Available Fields that are truly executable. If both Target Fields and Available Fields can express the same meaning, choose the field closer to the real source data.\n"
        "5) You may map aliases, abbreviations, colloquial expressions, or near-synonyms to the closest executable field and value, but do not invent nonexistent fields or values.\n"
        "6) Use sample rows, field value examples, and source data context to understand semantics such as time, region, category, version, status, and units.\n"
        "7) Fill sorting, quantity, and deduplication only when the user clearly asks for them.\n"
        "8) If the user request is completely invalid, irrelevant, or not executable, you may return ignore=true.\n"
    )
    return system_prompt, user_prompt_text


def _match_field_name(field: str, headers: list[str]) -> str:
    direct_key = _normalize_key(field)
    for header in headers:
        if _normalize_key(header) == direct_key:
            return header

    mapping = simple_match_excel_headers(headers, [field])
    return mapping.get(field, "")


def _normalize_operator(value: Any) -> str:
    operator = _normalize_text(value).lower()
    return _OPERATOR_ALIASES.get(operator, operator)


def _sanitize_field_requirements(raw_requirements: Any, headers: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_requirements, list):
        return []

    sanitized: list[dict[str, Any]] = []
    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        field = _normalize_text(_pick_value(item, "字段", "field"))
        matched_field = _match_field_name(field, headers) if field else ""
        if not matched_field:
            continue

        operator = _normalize_operator(_pick_value(item, "操作符", "operator"))
        if operator not in _ALLOWED_OPERATORS:
            continue

        value = _pick_value(item, "值", "value")
        value_text = _normalize_text(value) if value is not None else ""

        values = _as_string_list(_pick_value(item, "值列表", "values"))
        if operator in {"in", "not_in"} and not values and value_text:
            values = [chunk.strip() for chunk in re.split(r"[;,，；/|]", value_text) if chunk.strip()]

        sanitized.append(
            {
                "field": matched_field,
                "operator": operator,
                "value": value_text,
                "values": values,
            }
        )
    return sanitized


def _sanitize_sort_rules(raw_sort: Any, headers: list[str]) -> list[dict[str, str]]:
    if not isinstance(raw_sort, list):
        return []

    sanitized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_sort:
        if not isinstance(item, dict):
            continue
        field = _normalize_text(_pick_value(item, "字段", "field"))
        matched_field = _match_field_name(field, headers) if field else ""
        if not matched_field:
            continue
        direction = _normalize_text(_pick_value(item, "方向", "direction")).lower()
        if direction not in {"asc", "desc"}:
            direction = "asc"
        key = (matched_field, direction)
        if key in seen:
            continue
        seen.add(key)
        sanitized.append({"field": matched_field, "direction": direction})
    return sanitized


def _sanitize_rule_bundle(raw_plan: dict[str, Any], available_headers: list[str]) -> dict[str, Any]:
    standardized_requirements = _as_string_list(_pick_value(raw_plan, "规范化要求", "standardized_requirements"))
    field_requirements = _sanitize_field_requirements(_pick_value(raw_plan, "字段要求", "field_requirements"), available_headers)
    sort_rules = _sanitize_sort_rules(_pick_value(raw_plan, "排序", "sort"), available_headers)

    raw_row_limit = _pick_value(raw_plan, "行数限制", "row_limit")
    row_limit: int | None = None
    if isinstance(raw_row_limit, (int, float)):
        candidate = int(raw_row_limit)
        if candidate > 0:
            row_limit = candidate
    elif isinstance(raw_row_limit, str) and raw_row_limit.strip().isdigit():
        candidate = int(raw_row_limit.strip())
        if candidate > 0:
            row_limit = candidate

    dedupe_by: list[str] = []
    seen: set[str] = set()
    for item in _as_string_list(_pick_value(raw_plan, "去重字段", "dedupe_by")):
        matched = _match_field_name(item, available_headers)
        if not matched or matched in seen:
            continue
        seen.add(matched)
        dedupe_by.append(matched)

    ignore = _as_bool(_pick_value(raw_plan, "忽略", "ignore"))
    ignore_reason = _normalize_text(_pick_value(raw_plan, "忽略原因", "ignore_reason"))
    actionable = bool(field_requirements or sort_rules or row_limit or dedupe_by)
    if not actionable:
        ignore = True
        if not ignore_reason:
            ignore_reason = "没有可执行的字段规则"

    return {
        "ignore": ignore,
        "ignore_reason": ignore_reason,
        "standardized_requirements": standardized_requirements,
        "field_requirements": field_requirements,
        "sort": sort_rules,
        "row_limit": row_limit,
        "dedupe_by": dedupe_by,
        "actionable": actionable and not ignore,
    }


def _build_extraction_prompt(standardized_requirements: list[str]) -> str:
    if not standardized_requirements:
        return DEFAULT_PROMPT
    items = "\n".join(f"- {item}" for item in standardized_requirements)
    return f"{DEFAULT_PROMPT}\n\nAdditional normalized user requirements:\n{items}"


def resolve_user_rule_bundle(
    *,
    user_prompt: str,
    headers: list[str],
    settings: dict[str, Any],
    logger: Callable[[str], None] | None = None,
    context_text: str = "",
    template_filename: str = "",
    available_headers: list[str] | None = None,
    source_context_text: str = "",
    sample_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    raw_prompt = (user_prompt or "").strip()
    if not has_effective_user_prompt(raw_prompt):
        return {
            "enabled": False,
            "ignore": True,
            "ignore_reason": "empty or default prompt",
            "standardized_requirements": [],
            "field_requirements": [],
            "sort": [],
            "row_limit": None,
            "dedupe_by": [],
            "actionable": False,
            "extraction_prompt": DEFAULT_PROMPT,
        }

    merged_headers = _dedupe_headers(headers, available_headers or [])
    sample_payload = _build_sample_rows(sample_rows or [])
    field_value_examples = _build_field_value_examples(sample_rows or [])

    effective_prompt = raw_prompt
    if not _is_prepared_requirement_prompt(raw_prompt):
        try:
            understanding = _resolve_requirement_understanding(
                user_prompt=raw_prompt,
                settings=settings,
                logger=logger,
                template_filename=template_filename,
                target_headers=merged_headers,
                context_text=context_text,
            )
            effective_prompt = _compose_understood_prompt(understanding, raw_prompt)
        except Exception as exc:
            log_event(logger, f"[user rules] 理解阶段回退: {exc}")

    system_prompt, user_prompt_text = _build_rule_plan_messages(
        effective_prompt,
        headers,
        available_headers=merged_headers,
        context_text=context_text,
        template_filename=template_filename,
        source_context_text=source_context_text,
        sample_rows=sample_payload,
        field_value_examples=field_value_examples,
    )

    try:
        raw_plan = _request_rule_plan(
            settings=settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt_text,
        )
    except Exception as exc:
        log_event(logger, f"[user rules] ignored: planner failed ({exc})")
        return {
            "enabled": True,
            "ignore": True,
            "ignore_reason": "planner failed",
            "standardized_requirements": [],
            "field_requirements": [],
            "sort": [],
            "row_limit": None,
            "dedupe_by": [],
            "actionable": False,
            "extraction_prompt": DEFAULT_PROMPT,
        }

    bundle = _sanitize_rule_bundle(raw_plan, merged_headers)
    bundle["enabled"] = True
    bundle["extraction_prompt"] = _build_extraction_prompt(bundle["standardized_requirements"])

    if bundle["ignore"]:
        log_event(logger, f"[user rules] ignored: {bundle['ignore_reason']}")
        return bundle

    log_event(
        logger,
        "[user rules] standardized: "
        + json.dumps(bundle["standardized_requirements"], ensure_ascii=False),
    )
    log_event(
        logger,
        "[user rules] field requirements: "
        + json.dumps(
            {
                "conditions": bundle["field_requirements"],
                "sort": bundle["sort"],
                "row_limit": bundle["row_limit"],
                "dedupe_by": bundle["dedupe_by"],
            },
            ensure_ascii=False,
        ),
    )
    return bundle


def _try_parse_number(value: str) -> float | None:
    text = _normalize_text(value)
    if not text:
        return None

    multiplier = 1.0
    if "万亿" in text:
        multiplier = 1_000_000_000_000.0
    elif "亿" in text:
        multiplier = 100_000_000.0
    elif "万" in text:
        multiplier = 10_000.0

    cleaned = text
    for token in ("人民币", "元", "吨", "万元", "亿元", "万亿", "$", "￥", "%", "约", "约为", "共", "合计", "大约"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.replace(",", "").replace("，", "").strip()

    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None

    try:
        return float(match.group(0)) * multiplier
    except ValueError:
        return None


def _build_datetime_candidates(value: str) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []

    candidates: list[str] = []

    def add(candidate: str) -> None:
        candidate = _normalize_text(candidate.replace("T", " "))
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(text)
    add(text.replace("/", "-"))
    chinese = (
        text.replace("年", "-")
        .replace("月", "-")
        .replace("日", " ")
        .replace("号", " ")
        .replace("时", ":")
        .replace("分", ":")
        .replace("秒", "")
        .replace("/", "-")
    )
    chinese = re.sub(r"\s+", " ", chinese).strip(" -:")
    add(chinese)

    if "." in text and re.search(r"\d{4}\.\d{1,2}\.\d{1,2}", text):
        add(re.sub(r"(?<=\d)\.(?=\d{1,2}\.)", "-", text, count=1).replace(".", "-", 1))

    return candidates


def _try_parse_datetime(value: str) -> datetime | None:
    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
        "%Y%m",
    )
    for candidate in _build_datetime_candidates(value):
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def _compare_eq(left: str, right: str) -> bool:
    left_datetime = _try_parse_datetime(left)
    right_datetime = _try_parse_datetime(right)
    if left_datetime is not None and right_datetime is not None:
        return left_datetime == right_datetime

    left_number = _try_parse_number(left)
    right_number = _try_parse_number(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number

    return _normalize_key(left) == _normalize_key(right)


def _compare_order(left: str, right: str) -> tuple[float | datetime | None, float | datetime | None]:
    left_datetime = _try_parse_datetime(left)
    right_datetime = _try_parse_datetime(right)
    if left_datetime is not None and right_datetime is not None:
        return left_datetime, right_datetime

    left_number = _try_parse_number(left)
    right_number = _try_parse_number(right)
    if left_number is not None and right_number is not None:
        return left_number, right_number

    return None, None


def _collect_distinct_field_values(
    rows: list[dict[str, str]],
    field: str,
    *,
    scan_rows: int = 5000,
    max_values: int = 80,
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows[:scan_rows]:
        text = _normalize_text(row.get(field, ""))
        if not text:
            continue
        key = _normalize_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        values.append(text)
        if len(values) >= max_values:
            break
    return values


def _looks_like_free_text(value: str) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    if _try_parse_datetime(text) is not None:
        return False
    if _try_parse_number(text) is not None:
        return False
    return True


def _find_close_text_candidates(target: str, candidates: list[str]) -> list[str]:
    target_text = _normalize_text(target)
    target_key = _normalize_key(target_text)
    if not target_key:
        return []

    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        candidate_text = _normalize_text(candidate)
        candidate_key = _normalize_key(candidate_text)
        if not candidate_key:
            continue
        if candidate_key == target_key:
            return [candidate_text]

        score = 0.0
        if target_key in candidate_key or candidate_key in target_key:
            overlap = min(len(target_key), len(candidate_key))
            score = 1.0 + overlap / max(len(target_key), len(candidate_key), 1)
        else:
            ratio = SequenceMatcher(None, target_key, candidate_key).ratio()
            if ratio >= 0.84:
                score = ratio

        if score > 0:
            scored.append((score, candidate_text))

    scored.sort(key=lambda item: (-item[0], len(_normalize_key(item[1])), item[1]))
    ordered: list[str] = []
    seen: set[str] = set()
    for _, candidate in scored:
        key = _normalize_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def _reconcile_text_requirement(
    requirement: dict[str, Any],
    rows: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    operator = requirement.get("operator", "")
    field = requirement.get("field", "")
    if operator not in {"eq", "neq", "in", "not_in"} or not field:
        return requirement, None

    field_values = _collect_distinct_field_values(rows, field)
    if not field_values:
        return requirement, None

    original = {
        "field": field,
        "operator": operator,
        "value": requirement.get("value", ""),
        "values": list(requirement.get("values", []) or []),
    }
    updated = dict(requirement)
    changed = False

    if operator in {"eq", "neq"}:
        target = _normalize_text(requirement.get("value", ""))
        if not _looks_like_free_text(target):
            return requirement, None
        if any(_compare_eq(candidate, target) for candidate in field_values):
            return requirement, None

        close_candidates = _find_close_text_candidates(target, field_values)
        if len(close_candidates) == 1:
            updated["value"] = close_candidates[0]
            changed = True
        elif len(close_candidates) > 1:
            updated["operator"] = "contains" if operator == "eq" else "not_contains"
            updated["value"] = target
            updated["values"] = []
            changed = True

    if operator in {"in", "not_in"}:
        targets = [_normalize_text(item) for item in requirement.get("values", []) if _normalize_text(item)]
        if not targets:
            return requirement, None

        aligned_values: list[str] = []
        widened_targets: list[str] = []
        for target in targets:
            if not _looks_like_free_text(target):
                aligned_values.append(target)
                continue
            if any(_compare_eq(candidate, target) for candidate in field_values):
                aligned_values.append(target)
                continue
            close_candidates = _find_close_text_candidates(target, field_values)
            if len(close_candidates) == 1:
                aligned_values.append(close_candidates[0])
                if _normalize_key(close_candidates[0]) != _normalize_key(target):
                    changed = True
            elif len(close_candidates) > 1:
                widened_targets.append(target)
                changed = True
            else:
                aligned_values.append(target)

        deduped_values = _as_string_list(aligned_values)
        if widened_targets and not deduped_values:
            updated["operator"] = "contains" if operator == "in" else "not_contains"
            updated["value"] = widened_targets[0]
            updated["values"] = []
        else:
            updated["values"] = deduped_values

    if not changed:
        return requirement, None

    return updated, {"from": original, "to": updated}


def _reconcile_field_requirements(
    requirements: list[dict[str, Any]],
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reconciled: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for requirement in requirements:
        updated, adjustment = _reconcile_text_requirement(requirement, rows)
        reconciled.append(updated)
        if adjustment:
            adjustments.append(adjustment)
    return reconciled, adjustments


def _matches_requirement(row: dict[str, str], requirement: dict[str, Any]) -> bool:
    field = requirement["field"]
    if field not in row:
        return True
    operator = requirement["operator"]
    current = _normalize_text(row.get(field, ""))

    if operator == "not_empty":
        return bool(current)
    if operator == "empty":
        return not current

    target_value = _normalize_text(requirement.get("value", ""))
    target_values = [_normalize_text(item) for item in requirement.get("values", []) if _normalize_text(item)]

    if operator == "eq":
        return _compare_eq(current, target_value)
    if operator == "neq":
        return not _compare_eq(current, target_value)
    if operator == "contains":
        return bool(target_value) and _normalize_key(target_value) in _normalize_key(current)
    if operator == "not_contains":
        return not target_value or _normalize_key(target_value) not in _normalize_key(current)
    if operator == "in":
        return any(_compare_eq(current, item) for item in target_values)
    if operator == "not_in":
        return all(not _compare_eq(current, item) for item in target_values)

    left, right = _compare_order(current, target_value)
    if left is None or right is None:
        return False
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    return True


def _sort_key(value: str) -> tuple[int, Any]:
    datetime_value = _try_parse_datetime(value)
    if datetime_value is not None:
        return (0, datetime_value)

    number_value = _try_parse_number(value)
    if number_value is not None:
        return (1, number_value)

    return (2, _normalize_key(value))


def _validate_filtered_rows(
    *,
    original_rows: list[dict[str, str]],
    filtered_rows: list[dict[str, str]],
    field_requirements: list[dict[str, Any]],
    logger: Callable[[str], None] | None = None,
) -> None:
    if not field_requirements:
        return
    original_count = len(original_rows)
    filtered_count = len(filtered_rows)

    if original_count == 0:
        return
    if filtered_count == 0:
        log_event(logger, "[user rules] 校验提示: 当前条件执行后结果为空，请确认用户要求是否过严。")
        return
    if filtered_count == original_count:
        log_event(logger, "[user rules] 校验提示: 当前条件没有缩小候选范围，请确认是否有条件未生效。")


def apply_user_rule_bundle(
    rows: list[dict[str, str]],
    bundle: dict[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    if not rows:
        return rows
    if not bundle.get("enabled"):
        return rows
    if bundle.get("ignore") or not bundle.get("actionable"):
        return rows

    original_rows = rows
    filtered = rows
    reconciled_requirements, adjustments = _reconcile_field_requirements(
        list(bundle.get("field_requirements", [])),
        rows,
    )

    if adjustments:
        log_event(
            logger,
            "[user rules] reconciled requirements: " + json.dumps(adjustments, ensure_ascii=False),
        )

    for requirement in reconciled_requirements:
        filtered = [row for row in filtered if _matches_requirement(row, requirement)]

    for sort_rule in reversed(bundle.get("sort") or []):
        field = sort_rule["field"]
        reverse = sort_rule.get("direction") == "desc"
        filtered = sorted(filtered, key=lambda row: _sort_key(str(row.get(field, ""))), reverse=reverse)

    dedupe_by = bundle.get("dedupe_by") or []
    if dedupe_by:
        unique_rows: list[dict[str, str]] = []
        seen: set[tuple[str, ...]] = set()
        for row in filtered:
            key = tuple(_normalize_key(row.get(field, "")) for field in dedupe_by)
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(row)
        filtered = unique_rows

    row_limit = bundle.get("row_limit")
    if isinstance(row_limit, int) and row_limit > 0:
        filtered = filtered[:row_limit]

    _validate_filtered_rows(
        original_rows=original_rows,
        filtered_rows=filtered,
        field_requirements=reconciled_requirements,
        logger=logger,
    )
    log_event(logger, f"[user rules] filtered rows {len(original_rows)} -> {len(filtered)}")
    return filtered


__all__ = [
    "apply_user_rule_bundle",
    "has_effective_user_prompt",
    "resolve_scope_user_prompts",
    "resolve_user_rule_bundle",
]
