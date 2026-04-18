from __future__ import annotations

from difflib import SequenceMatcher
import json
import re
from typing import Any


COLOR_NAME_MAP = {
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#00FF00",
    "yellow": "#FFFF00",
    "purple": "#800080",
    "orange": "#FFA500",
    "black": "#000000",
    "white": "#FFFFFF",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "gray": "#808080",
    "grey": "#808080",
    "红色": "#FF0000",
    "蓝色": "#0000FF",
    "绿色": "#00FF00",
    "黄色": "#FFFF00",
    "紫色": "#800080",
    "橙色": "#FFA500",
    "黑色": "#000000",
    "白色": "#FFFFFF",
    "灰色": "#808080",
}
FORMAT_MUTATION_FIELDS = (
    "bold",
    "italic",
    "underline",
    "color",
    "font_name",
    "font_size",
    "alignment",
    "heading_level",
    "line_spacing",
    "space_before",
    "space_after",
)
BOOLEAN_FORMAT_FIELDS = {"bold", "italic", "underline"}
FORMAT_TARGET_FIELDS = {"paragraph_index", "line_index", "reference_text", "run_indices"}
FORMAT_RESET_PATTERNS = (
    "重置样式",
    "恢复默认样式",
    "清除格式",
    "移除格式",
)


def _normalize_modifications_payload(raw_payload: str) -> list[dict[str, Any]]:
    payload = raw_payload or "[]"
    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        parsed = parsed.get("modifications", [])
    if not isinstance(parsed, list):
        raise ValueError("修改方案必须是数组")
    return [item for item in parsed if isinstance(item, dict)]


def _infer_format_update_policy(instruction: str) -> dict[str, Any]:
    prompt = str(instruction or "").strip()
    normalized = prompt.lower()
    allowed_fields: set[str] = set()
    explicit_false_fields: set[str] = set()
    reset_mode = any(pattern in prompt for pattern in FORMAT_RESET_PATTERNS)

    if reset_mode:
        allowed_fields.update(FORMAT_MUTATION_FIELDS)

    color_pattern = re.compile(
        r"(#?[0-9a-fA-F]{6}|红色|蓝色|绿色|黄色|紫色|橙色|黑色|白色|灰色|red|blue|green|yellow|purple|orange|black|white|gray|grey|变红|变蓝|变绿|变黄|变紫|变橙|变黑|变白|变灰|改红|改蓝|改绿|改黄|改紫|改橙|改黑|改白|改灰)",
        flags=re.IGNORECASE,
    )
    if color_pattern.search(prompt):
        allowed_fields.add("color")

    boolean_field_patterns = {
        "bold": (
            re.compile(r"(取消|去掉|移除|去除|清除|不要|不再)\s*(加粗|粗体)|(加粗|粗体)\s*(取消|去掉|移除|去除|清除)|不加粗"),
            re.compile(r"加粗|粗体"),
        ),
        "italic": (
            re.compile(r"(取消|去掉|移除|去除|清除|不要|不再)\s*(斜体)|(斜体)\s*(取消|去掉|移除|去除|清除)|不斜体"),
            re.compile(r"斜体"),
        ),
        "underline": (
            re.compile(r"(取消|去掉|移除|去除|清除|不要|不再)\s*(下划线)|(下划线)\s*(取消|去掉|移除|去除|清除)|不要下划线|不加下划线"),
            re.compile(r"下划线"),
        ),
    }
    for field_name, (negative_pattern, positive_pattern) in boolean_field_patterns.items():
        if negative_pattern.search(prompt):
            allowed_fields.add(field_name)
            explicit_false_fields.add(field_name)
            continue
        if positive_pattern.search(prompt):
            allowed_fields.add(field_name)

    if re.search(
        r'(?:字体(?:改为|设为|用)?|font(?:\s*family)?(?:\s*[:：]|设为|改为)?)[“"「]?([A-Za-z][A-Za-z0-9 \-]+|微软雅黑|宋体|仿宋|楷体|黑体|PingFang SC|Arial|Times New Roman)[”"」]?',
        prompt,
        flags=re.IGNORECASE,
    ):
        allowed_fields.add("font_name")

    if re.search(r'(\d+(?:\.\d+)?)\s*(?:px|pt|磅|号)', prompt, flags=re.IGNORECASE):
        allowed_fields.add("font_size")

    if any(token in prompt for token in ("居中", "居中对齐", "中心对齐", "右对齐", "居右", "左对齐", "居左", "两端对齐")):
        allowed_fields.add("alignment")

    if any(token in prompt for token in ("一级标题", "二级标题", "三级标题", "标题级别", "改成正文")):
        allowed_fields.add("heading_level")

    if re.search(r'行距(?:调整为|设为|改为)?\s*\d+(?:\.\d+)?', prompt):
        allowed_fields.add("line_spacing")
    if re.search(r'段前(?:间距)?(?:调整为|设为|改为)?\s*\d+(?:\.\d+)?', prompt):
        allowed_fields.add("space_before")
    if re.search(r'段后(?:间距)?(?:调整为|设为|改为)?\s*\d+(?:\.\d+)?', prompt):
        allowed_fields.add("space_after")

    return {
        "allowed_fields": sorted(allowed_fields),
        "explicit_false_fields": sorted(explicit_false_fields),
        "reset_mode": reset_mode,
        "raw_instruction": normalized,
    }


def _sanitize_text_run_format_modification(
    modification: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    allowed_fields = set(policy.get("allowed_fields") or [])
    explicit_false_fields = set(policy.get("explicit_false_fields") or [])
    reset_mode = bool(policy.get("reset_mode"))

    sanitized: dict[str, Any] = {"type": "text_run_format"}
    for field_name in FORMAT_TARGET_FIELDS:
        if modification.get(field_name) is not None:
            sanitized[field_name] = modification[field_name]

    for field_name in FORMAT_MUTATION_FIELDS:
        if field_name not in modification:
            continue
        if field_name not in allowed_fields and not reset_mode:
            continue

        value = modification[field_name]
        if field_name in BOOLEAN_FORMAT_FIELDS:
            bool_value = _coerce_optional_bool(value)
            if bool_value is None:
                continue
            if bool_value is False and field_name not in explicit_false_fields and not reset_mode:
                continue
            sanitized[field_name] = bool_value
            continue

        sanitized[field_name] = value

    if not any(field_name in sanitized for field_name in FORMAT_MUTATION_FIELDS):
        return None

    normalized = _normalize_ai_modification(sanitized)
    if normalized is None:
        return None
    if not any(field_name in normalized for field_name in FORMAT_MUTATION_FIELDS):
        return None
    return normalized


def _sanitize_modifications_for_instruction(
    modifications: list[dict[str, Any]],
    instruction: str,
) -> list[dict[str, Any]]:
    if not modifications:
        return []

    policy = _infer_format_update_policy(instruction)
    sanitized_modifications: list[dict[str, Any]] = []

    for modification in modifications:
        modification_type = _normalize_modification_type(modification.get("type"))
        if modification_type == "text_run_format":
            sanitized = _sanitize_text_run_format_modification(modification, policy)
            if sanitized:
                sanitized_modifications.append(sanitized)
            continue
        sanitized_modifications.append(modification)

    return _deduplicate_modifications(sanitized_modifications)


def _parse_ai_modifications(ai_response: str) -> list[dict[str, Any]]:
    modifications: list[dict[str, Any]] = []
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\[\s*{.*?}\s*\])",
        r"({\s*\"modifications\".*?})",
    ]

    for pattern in patterns:
        for matched_text in re.findall(pattern, ai_response, flags=re.DOTALL):
            try:
                parsed = json.loads(matched_text.strip())
            except json.JSONDecodeError:
                continue

            raw_items: list[dict[str, Any]]
            if isinstance(parsed, list):
                raw_items = [item for item in parsed if isinstance(item, dict)]
            elif isinstance(parsed, dict) and isinstance(parsed.get("modifications"), list):
                raw_items = [item for item in parsed["modifications"] if isinstance(item, dict)]
            elif isinstance(parsed, dict):
                raw_items = [parsed]
            else:
                continue

            for raw_item in raw_items:
                normalized_item = _normalize_ai_modification(raw_item)
                if normalized_item:
                    modifications.append(normalized_item)

            if modifications:
                return modifications

    fallback_item = _infer_modification_from_text(ai_response)
    return [fallback_item] if fallback_item else []


def _parse_ordinal_index(token: str) -> int | None:
    normalized = str(token or "").strip()
    if not normalized:
        return None

    if normalized.isdigit():
        value = int(normalized)
        return value - 1 if value > 0 else 0

    digit_map = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }

    if normalized == "十":
        return 9

    if normalized.startswith("十"):
        tail = digit_map.get(normalized[1:], 0)
        return 9 + tail

    if normalized.endswith("十"):
        head = digit_map.get(normalized[0], 0)
        return head * 10 - 1 if head else None

    if "十" in normalized:
        head_token, tail_token = normalized.split("十", 1)
        head = digit_map.get(head_token, 1)
        tail = digit_map.get(tail_token, 0)
        return head * 10 + tail - 1

    if normalized in digit_map:
        return digit_map[normalized] - 1

    return None


def _deduplicate_modifications(modifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for modification in modifications:
        signature = json.dumps(modification, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(modification)

    return deduplicated


def _infer_modifications_from_instruction(instruction: str) -> list[dict[str, Any]]:
    prompt = str(instruction or "").strip()
    if not prompt:
        return []

    modifications: list[dict[str, Any]] = []

    for match in re.finditer(
        r'(?:将|把)?[“"「](?P<old>.+?)[”"」]\s*(?:替换为|替换成|改为|改成)\s*[“"「](?P<new>.+?)[”"」]',
        prompt,
    ):
        old_text = match.group("old").strip()
        new_text = match.group("new").strip()
        if old_text:
            modifications.append({
                "type": "replace_text",
                "old_text": old_text,
                "new_text": new_text,
            })

    for match in re.finditer(
        r'在(?:第\s*(?P<ordinal>[一二三四五六七八九十两0-9]+)\s*(?P<unit>段|行)|[“"「](?P<reference>.+?)[”"」]|开头|结尾|末尾)(?:的)?(?P<position>前|后)?插入[：:\s]*[“"「](?P<text>.+?)[”"」]',
        prompt,
    ):
        insert_text = match.group("text").strip()
        if not insert_text:
            continue

        modification: dict[str, Any] = {"type": "insert_text", "text": insert_text}
        ordinal = match.group("ordinal")
        unit = match.group("unit")
        reference_text = (match.group("reference") or "").strip()
        position_token = match.group("position")

        if "开头" in match.group(0):
            modification["position"] = "start"
        elif "结尾" in match.group(0) or "末尾" in match.group(0):
            modification["position"] = "end"
        elif position_token == "前":
            modification["position"] = "before"
        elif position_token == "后":
            modification["position"] = "after"
        else:
            modification["position"] = "end"

        if ordinal:
            parsed_index = _parse_ordinal_index(ordinal)
            if parsed_index is not None:
                if unit == "行":
                    modification["line_index"] = parsed_index
                else:
                    modification["paragraph_index"] = parsed_index
        elif reference_text:
            modification["reference_text"] = reference_text

        modifications.append(modification)

    format_modification: dict[str, Any] = {"type": "text_run_format"}

    target_match = re.search(r'第\s*([一二三四五六七八九十两0-9]+)\s*(段|行)', prompt)
    if target_match:
        parsed_index = _parse_ordinal_index(target_match.group(1))
        if parsed_index is not None:
            if target_match.group(2) == "行":
                format_modification["line_index"] = parsed_index
            else:
                format_modification["paragraph_index"] = parsed_index
    elif "标题" in prompt:
        format_modification["paragraph_index"] = 0
    else:
        quoted_targets = re.findall(r'[“"「](.+?)[”"」]', prompt)
        if quoted_targets and not modifications:
            format_modification["reference_text"] = quoted_targets[0].strip()

    if "加粗" in prompt:
        format_modification["bold"] = True
    if "斜体" in prompt:
        format_modification["italic"] = True
    if "下划线" in prompt:
        format_modification["underline"] = True

    color_match = re.search(r'(#?[0-9a-fA-F]{6}|红色|蓝色|绿色|黄色|紫色|橙色|黑色|白色|灰色|red|blue|green|yellow|purple|orange|black|white|gray|grey)', prompt, flags=re.IGNORECASE)
    if color_match:
        normalized_color = _normalize_color(color_match.group(1))
        if normalized_color:
            format_modification["color"] = normalized_color

    font_match = re.search(r'(?:字体(?:改为|设为|用)?|font(?:\s*family)?(?:\s*[:：]|设为|改为)?)[“"「]?([A-Za-z][A-Za-z0-9 \-]+|微软雅黑|宋体|仿宋|楷体|黑体|PingFang SC|Arial|Times New Roman)[”"」]?', prompt, flags=re.IGNORECASE)
    if font_match:
        format_modification["font_name"] = font_match.group(1).strip()

    font_size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:px|pt|磅|号)', prompt, flags=re.IGNORECASE)
    if font_size_match:
        format_modification["font_size"] = float(font_size_match.group(1))

    if "居中" in prompt or "居中对齐" in prompt or "中心对齐" in prompt:
        format_modification["alignment"] = "center"
    elif "右对齐" in prompt or "居右" in prompt:
        format_modification["alignment"] = "right"
    elif "左对齐" in prompt or "居左" in prompt:
        format_modification["alignment"] = "left"
    elif "两端对齐" in prompt:
        format_modification["alignment"] = "justify"

    if "一级标题" in prompt:
        format_modification["heading_level"] = 1
    elif "二级标题" in prompt:
        format_modification["heading_level"] = 2
    elif "三级标题" in prompt:
        format_modification["heading_level"] = 3
    elif "正文" in prompt and ("标题级别" in prompt or "改成正文" in prompt):
        format_modification["heading_level"] = 0

    line_spacing_match = re.search(r'行距(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if line_spacing_match:
        format_modification["line_spacing"] = float(line_spacing_match.group(1))

    space_before_match = re.search(r'段前(?:间距)?(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if space_before_match:
        format_modification["space_before"] = float(space_before_match.group(1))

    space_after_match = re.search(r'段后(?:间距)?(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if space_after_match:
        format_modification["space_after"] = float(space_after_match.group(1))

    if any(key in format_modification for key in (
        "bold",
        "italic",
        "underline",
        "color",
        "font_name",
        "font_size",
        "alignment",
        "heading_level",
        "line_spacing",
        "space_before",
        "space_after",
    )) and any(key in format_modification for key in ("paragraph_index", "reference_text", "line_index")):
        modifications.append(format_modification)

    return _deduplicate_modifications(modifications)


def _normalize_ai_modification(raw_item: dict[str, Any]) -> dict[str, Any] | None:
    normalized_type = _normalize_modification_type(raw_item.get("type"))
    if normalized_type is None:
        return None

    normalized: dict[str, Any] = {"type": normalized_type}

    paragraph_index = raw_item.get("paragraph_index", raw_item.get("paragraphIndex"))
    if paragraph_index is not None:
        try:
            normalized["paragraph_index"] = int(paragraph_index)
        except (TypeError, ValueError):
            return None

    line_index = raw_item.get("line_index", raw_item.get("lineIndex"))
    if line_index is not None:
        try:
            normalized["line_index"] = int(line_index)
        except (TypeError, ValueError):
            normalized.pop("line_index", None)

    reference_text = raw_item.get("reference_text", raw_item.get("referenceText"))
    if reference_text is not None:
        reference_text = str(reference_text).strip()
        if reference_text:
            normalized["reference_text"] = reference_text

    run_indices = raw_item.get("run_indices", raw_item.get("runIndices"))
    if isinstance(run_indices, list):
        normalized["run_indices"] = _normalize_run_indices(run_indices)

    for key in ("old_text", "new_text", "text", "font_name", "alignment"):
        value = raw_item.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value != "":
            normalized[key] = value

    for nested_key in ("changes", "format_changes", "properties"):
        nested_value = raw_item.get(nested_key)
        if not isinstance(nested_value, dict):
            continue
        for key in (
            "bold",
            "italic",
            "underline",
            "color",
            "font_name",
            "font_size",
            "alignment",
            "heading_level",
            "line_spacing",
            "space_before",
            "space_after",
        ):
            if key not in normalized and nested_value.get(key) is not None:
                normalized[key] = nested_value[key]

    for bool_key in ("bold", "italic", "underline"):
        bool_value = _coerce_optional_bool(raw_item.get(bool_key))
        if bool_value is not None:
            normalized[bool_key] = bool_value
        elif bool_key in normalized:
            nested_bool_value = _coerce_optional_bool(normalized[bool_key])
            if nested_bool_value is None:
                normalized.pop(bool_key, None)
            else:
                normalized[bool_key] = nested_bool_value

    normalized_position = _normalize_insert_position(raw_item.get("position", normalized.get("position")))
    if normalized_position:
        normalized["position"] = normalized_position
    else:
        normalized.pop("position", None)

    if raw_item.get("color") is not None and "color" not in normalized:
        normalized["color"] = raw_item["color"]
    if raw_item.get("font_size") is not None and "font_size" not in normalized:
        normalized["font_size"] = raw_item["font_size"]
    if raw_item.get("heading_level") is not None and "heading_level" not in normalized:
        normalized["heading_level"] = raw_item["heading_level"]
    if raw_item.get("line_spacing") is not None and "line_spacing" not in normalized:
        normalized["line_spacing"] = raw_item["line_spacing"]
    if raw_item.get("space_before") is not None and "space_before" not in normalized:
        normalized["space_before"] = raw_item["space_before"]
    if raw_item.get("space_after") is not None and "space_after" not in normalized:
        normalized["space_after"] = raw_item["space_after"]

    if "color" in normalized:
        normalized_color = _normalize_color(normalized["color"])
        if normalized_color:
            normalized["color"] = normalized_color
        else:
            normalized.pop("color", None)

    for numeric_key in ("font_size", "line_spacing", "space_before", "space_after"):
        if numeric_key not in normalized:
            continue
        try:
            normalized[numeric_key] = float(normalized[numeric_key])
        except (TypeError, ValueError):
            normalized.pop(numeric_key, None)

    if "heading_level" in normalized:
        try:
            normalized["heading_level"] = max(0, min(3, int(normalized["heading_level"])))
        except (TypeError, ValueError):
            normalized.pop("heading_level", None)

    if "alignment" in normalized:
        normalized_alignment = _normalize_alignment(normalized["alignment"])
        if normalized_alignment is None:
            normalized.pop("alignment", None)
        else:
            normalized["alignment"] = normalized_alignment

    if normalized["type"] == "text_run_format" and not any(
        key in normalized for key in ("paragraph_index", "reference_text", "line_index")
    ):
        return None
    if normalized["type"] == "replace_text" and not str(normalized.get("old_text") or "").strip():
        return None
    if normalized["type"] == "insert_text" and not str(normalized.get("text") or "").strip():
        return None
    return normalized


def _infer_modification_from_text(ai_response: str) -> dict[str, Any] | None:
    text = (ai_response or "").lower()
    if "加粗" not in text and "red" not in text and "红色" not in text:
        return None

    fallback: dict[str, Any] = {"type": "text_run_format", "paragraph_index": 0}
    if "加粗" in text or "bold" in text:
        fallback["bold"] = True
    if "红色" in text or "red" in text:
        fallback["color"] = "#FF0000"
    return fallback


def _extract_text_explanation(ai_response: str) -> str:
    text = re.sub(r"```json\s*.*?\s*```", "", ai_response or "", flags=re.DOTALL)
    text = re.sub(r"```\s*.*?\s*```", "", text, flags=re.DOTALL)
    return text.strip()


def _normalize_color(value: Any) -> str | None:
    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None

    lowered = raw_value.lower()
    raw_value = COLOR_NAME_MAP.get(lowered, raw_value)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw_value):
        return raw_value.upper()
    if re.fullmatch(r"[0-9a-fA-F]{6}", raw_value):
        return f"#{raw_value.upper()}"
    return None


def _normalize_alignment(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    alignment_map = {
        "left": "left",
        "start": "left",
        "居左": "left",
        "左对齐": "left",
        "center": "center",
        "centre": "center",
        "居中": "center",
        "居中对齐": "center",
        "right": "right",
        "end": "right",
        "居右": "right",
        "右对齐": "right",
        "justify": "justify",
        "两端对齐": "justify",
    }
    return alignment_map.get(normalized)


def _normalize_modification_type(value: Any) -> str | None:
    normalized = str(value or "text_run_format").strip().lower()
    type_map = {
        "text_run_format": "text_run_format",
        "format_text": "text_run_format",
        "format": "text_run_format",
        "style": "text_run_format",
        "样式": "text_run_format",
        "replace_text": "replace_text",
        "replace": "replace_text",
        "替换": "replace_text",
        "insert_text": "insert_text",
        "insert": "insert_text",
        "插入": "insert_text",
    }
    return type_map.get(normalized)


def _normalize_run_indices(raw_indices: list[Any]) -> list[int]:
    normalized_indices: list[int] = []
    for item in raw_indices:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index < 0 or index in normalized_indices:
            continue
        normalized_indices.append(index)
    return normalized_indices


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "是", "开启", "开"}:
        return True
    if normalized in {"false", "0", "no", "n", "否", "关闭", "关"}:
        return False
    return None


def _normalize_insert_position(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    position_map = {
        "before": "before",
        "前": "before",
        "after": "after",
        "后": "after",
        "start": "start",
        "beginning": "start",
        "prepend": "start",
        "开头": "start",
        "头部": "start",
        "end": "end",
        "append": "end",
        "结尾": "end",
        "末尾": "end",
    }
    return position_map.get(normalized)


def _normalize_match_text(value: Any) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]", "", normalized)


def _find_best_matching_paragraph(paragraphs: list[Any], reference_text: str) -> int | None:
    normalized_reference = _normalize_match_text(reference_text)
    if not normalized_reference:
        return None

    best_index: int | None = None
    best_score = 0.0
    for index, paragraph in enumerate(paragraphs):
        candidate = _normalize_match_text(paragraph.text)
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized_reference, candidate).ratio()
        if score > best_score:
            best_score = score
            best_index = index

    if best_score >= 0.58:
        return best_index
    return None


__all__ = [
    "_coerce_optional_bool",
    "_deduplicate_modifications",
    "_extract_text_explanation",
    "_find_best_matching_paragraph",
    "_infer_format_update_policy",
    "_infer_modification_from_text",
    "_infer_modifications_from_instruction",
    "_normalize_ai_modification",
    "_normalize_alignment",
    "_normalize_color",
    "_normalize_insert_position",
    "_normalize_match_text",
    "_normalize_modification_type",
    "_normalize_modifications_payload",
    "_normalize_run_indices",
    "_parse_ai_modifications",
    "_parse_ordinal_index",
    "_sanitize_modifications_for_instruction",
    "_sanitize_text_run_format_modification",
]
