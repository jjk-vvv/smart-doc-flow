from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..core.format.xlsx_artifact_io import (
    load_xlsx_sheet_rows_artifact,
    load_xlsx_workbook_manifest,
)
from .response_planner import (
    is_broad_document_question,
    is_strict_minimal_request,
    should_prefer_frontend_grounding,
)
from .intent_router import is_document_risk_review_question
from .text_utils import normalize_markdown_text


def trim_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def sanitize_prompt_context_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        priority_order = {
            "current_document": 0,
            "table_row_samples": 1,
            "current_locked_object": 2,
            "top_fields": 3,
            "table_column_headers": 4,
            "figure_key_points": 5,
            "summary": 6,
            "file_name": 7,
            "file_hash": 8,
            "documents": 9,
        }
        ordered_items = list(value.items())
        ordered_items.sort(
            key=lambda pair: priority_order.get(str(pair[0] or "").strip().lower(), 999)
        )
        for key, item in ordered_items[:20]:
            normalized_key = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(key or "").strip())[:48].strip("_")
            if not normalized_key:
                continue
            normalized_item = sanitize_prompt_context_value(item, depth=depth + 1)
            if normalized_item in (None, "", [], {}):
                continue
            cleaned[normalized_key] = normalized_item
        return cleaned
    if isinstance(value, (list, tuple)):
        cleaned_items = [
            sanitize_prompt_context_value(item, depth=depth + 1)
            for item in list(value)[:24]
        ]
        return [item for item in cleaned_items if item not in (None, "", [], {})]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6) if isinstance(value, float) else int(value)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return None
    return trim_text(text, 240)


def normalize_frontend_context(extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(extra_context, dict):
        return {}
    normalized = sanitize_prompt_context_value(extra_context)
    return normalized if isinstance(normalized, dict) else {}


def frontend_context_block(extra_context: Optional[Dict[str, Any]]) -> str:
    compact = normalize_frontend_context(extra_context)
    if not compact:
        return ""
    payload = trim_text(json.dumps(compact, ensure_ascii=False), 4500)
    return (
        "[Frontend active document snapshot]\n"
        "Treat the JSON below as the latest UI-visible snapshot of the user's current document selection.\n"
        "Use it to ground the answer when it already contains the exact fact the user is asking for.\n"
        "Do not invent placeholders for missing specifics.\n"
        "If the snapshot is still insufficient, say exactly which key detail is still missing.\n"
        f"{payload}"
    )


def build_frontend_evidence_dossier(extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    compact = normalize_frontend_context(extra_context)
    if not compact:
        return {}
    current_document = compact.get("current_document") if isinstance(compact.get("current_document"), dict) else {}
    if not current_document:
        return {}
    file_name = trim_text(current_document.get("file_name"), 220)
    file_hash = trim_text(current_document.get("file_hash"), 120)
    summary = trim_text(current_document.get("summary"), 900)
    top_fields = extract_frontend_top_fields(current_document.get("top_fields"))
    table_column_headers = (
        [str(item).strip() for item in current_document.get("table_column_headers", [])[:10] if str(item or "").strip()]
        if isinstance(current_document.get("table_column_headers"), list)
        else []
    )
    figure_key_points = (
        [str(item).strip() for item in current_document.get("figure_key_points", [])[:6] if str(item or "").strip()]
        if isinstance(current_document.get("figure_key_points"), list)
        else []
    )
    available_years, has_quarter = _collect_time_hints(
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
        table_column_headers=table_column_headers,
        figure_key_points=figure_key_points,
    )
    core_candidates = _preferred_verification_fields(top_fields, limit=3)
    card_candidates = []
    for field in core_candidates:
        label = str(field.get("label") or "").strip()
        value = trim_text(field.get("value"), 160)
        if not label or not value:
            continue
        card_candidates.append({"label": label, "value": value})
    return {
        "file_name": file_name,
        "file_hash": file_hash,
        "summary": summary,
        "top_fields": [
            {
                "label": str(field.get("label") or "").strip(),
                "value": trim_text(field.get("value"), 180),
                "confidence": field.get("confidence"),
                "page": field.get("page"),
            }
            for field in top_fields[:8]
            if str(field.get("label") or "").strip() and str(field.get("value") or "").strip()
        ],
        "coverage": {
            "years": available_years[:8],
            "has_quarter_level": bool(has_quarter),
            "table_column_headers": table_column_headers[:8],
            "figure_key_points": figure_key_points[:4],
        },
        "card_candidates": card_candidates[:3],
        "evidence_policy": {
            "must_not_assume_missing_year_or_quarter": True,
            "must_not_invent_field_values": True,
            "fallback_when_missing": "state missing key detail explicitly",
        },
    }


def frontend_evidence_dossier_block(
    *,
    user_message: str,
    extra_context: Optional[Dict[str, Any]],
) -> str:
    dossier = build_frontend_evidence_dossier(extra_context)
    if not dossier:
        return ""
    payload = trim_text(json.dumps(dossier, ensure_ascii=False), 4200)
    normalized_question = str(user_message or "").strip()
    return (
        "[Frontend evidence dossier]\n"
        "Use this dossier first for field picks, provenance explanation, and year/quarter coverage checks.\n"
        "If the requested value is outside dossier coverage, explicitly say it is missing instead of guessing.\n"
        f"Question: {normalized_question}\n"
        f"Dossier: {payload}"
    )


def cleanup_answer_text(answer: str) -> str:
    return normalize_markdown_text(str(answer or ""))


def _summary_short_circuit_ready(extra_context: Optional[Dict[str, Any]]) -> bool:
    dossier = build_frontend_evidence_dossier(extra_context)
    if not dossier:
        return False
    summary = str(dossier.get("summary") or "").strip()
    top_fields = dossier.get("top_fields")
    if looks_like_placeholder_answer(summary):
        return False
    return bool(summary) and isinstance(top_fields, list) and len(top_fields) >= 2


def is_summary_with_field_inventory_question(question: str) -> bool:
    text = str(question or "").strip()
    lowered = text.lower()
    if not is_broad_document_question(text):
        return False
    field_markers = (
        "字段",
        "关键字段",
        "核心字段",
        "top field",
        "key field",
        "field list",
    )
    count_markers = (
        "3个",
        "3 个",
        "3个字段",
        "3 个字段",
        "三个",
        "三个字段",
        "3 项",
        "三项",
        "3 fields",
        "three fields",
        "three key fields",
    )
    has_field_hint = any(marker in text for marker in field_markers) or any(marker in lowered for marker in field_markers)
    has_count_hint = any(marker in text for marker in count_markers) or any(marker in lowered for marker in count_markers)
    return has_field_hint and has_count_hint


def wants_json_like_output(question: str) -> bool:
    lowered = str(question or "").lower()
    return any(marker in lowered for marker in ("json", "json格式", "结构化", "structured", "array", "object"))


def is_entity_extraction_question(question: str) -> bool:
    text = str(question or "").strip()
    lowered = text.lower()
    if any(marker in lowered for marker in ("postgres", "postgresql", "schema", "ddl", "create table", "table design")):
        return False
    extraction_markers = ("抽取", "提取", "抽出", "extract", "pull out")
    entity_markers = ("实体", "字段", "指标", "关键信息", "entity", "entities", "field", "fields")
    action_markers = ("请", "帮我", "给我", "把", "将", "返回", "输出", "列出", "extract", "return", "list")
    method_markers = ("如何", "怎么", "优化", "提升", "方案", "评估", "how to", "improve", "best practice")
    doc_markers = (
        "文档",
        "文件",
        "表格",
        "当前文档",
        "this document",
        "this file",
        "selected document",
        "current document",
    )

    has_extract = any(marker in text for marker in extraction_markers) or any(marker in lowered for marker in extraction_markers)
    has_entity = any(marker in text for marker in entity_markers) or any(marker in lowered for marker in entity_markers)
    has_action = any(marker in text for marker in action_markers) or any(marker in lowered for marker in action_markers)
    has_doc_hint = any(marker in text for marker in doc_markers) or any(marker in lowered for marker in doc_markers)
    asks_method = any(marker in text for marker in method_markers) or any(marker in lowered for marker in method_markers)
    has_list_hint = bool(re.search(r"[、,，;；/]|(?:以及|和|与| and )", text))

    if asks_method and not has_doc_hint:
        return False
    if re.search(r"\bextract(?:ing)?\b.{0,32}\b(fields?|entities?)\b", lowered):
        return True
    if wants_json_like_output(text) and has_entity and has_doc_hint:
        return True
    if has_extract and has_entity and (has_action or has_doc_hint):
        return True
    return has_extract and has_doc_hint and (has_list_hint or wants_json_like_output(text))


def _normalize_entity_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).strip().lower()


ENTITY_ALIAS_MAP = {
    "year": ("年份", "年度", "统计年份"),
    "统计年份": ("年份", "年度", "year"),
    "title": ("标题", "文档标题", "文件标题"),
    "file_name": ("文件名", "文档名", "标题"),
    "pm25": ("pm2.5", "pm2_5", "pm 2.5"),
}


def _entity_alias_candidates(token: str) -> List[str]:
    normalized = _normalize_entity_key(token)
    if not normalized:
        return []
    candidates = {normalized}
    for canonical, aliases in ENTITY_ALIAS_MAP.items():
        alias_keys = {_normalize_entity_key(canonical)}
        alias_keys.update(_normalize_entity_key(item) for item in aliases)
        if normalized in alias_keys:
            candidates.update(alias_keys)
    return [item for item in candidates if item]


def extract_requested_entities(question: str) -> List[str]:
    text = str(question or "").strip()
    if not text:
        return []

    quoted = [
        item.strip()
        for item in re.findall(r"[\"'“”‘’「」《》](.{1,32}?)[\"'“”‘’「」《》]", text)
        if str(item or "").strip()
    ]
    cleaned = re.sub(
        r"(请|帮我|给我|返回|输出|列出|抽取|提取|抽出|json|格式|结构化|extract|return|list)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    tokens = [
        item.strip()
        for item in re.split(r"(?:[，,。；;、/\n\t|]|(?:和|与|及|以及)|\band\b)+", cleaned, flags=re.IGNORECASE)
        if str(item or "").strip()
    ]
    stop_tokens = {
        "字段",
        "实体",
        "指标",
        "当前文档",
        "当前文件",
        "这份文档",
        "这个文件",
        "this document",
        "this file",
        "current document",
        "selected document",
        "current file",
        "并按",
        "并且",
        "然后",
        "以及",
        "json",
        "json输出",
    }
    stop_keys = {_normalize_entity_key(item) for item in stop_tokens}

    merged: List[str] = []
    for token in quoted + tokens:
        token = re.sub(
            r"\b(?:please|from|current|document|selected|bound|only|and|return|json)\b",
            " ",
            str(token or ""),
            flags=re.IGNORECASE,
        )
        token = re.sub(
            r"^\s*(?:从)?(?:当前文档|当前文件|这份文档|这个文件|该文档|文档)(?:中|里|内)?\s*",
            "",
            token,
        )
        token = re.sub(r"^\s*(?:fields?|entities?)\s+", "", token, flags=re.IGNORECASE)
        token = re.sub(r"\s+", " ", token).strip(" .,:;!?")
        normalized = _normalize_entity_key(token)
        if not normalized or normalized.isdigit():
            continue
        if token in stop_tokens or normalized in stop_keys:
            continue
        merged.append(token)

    unique: List[str] = []
    seen: set[str] = set()
    for token in merged:
        norm = _normalize_entity_key(token)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(token)
    return unique[:8]


def _match_entity_token_to_field(token: str, top_fields: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    alias_candidates = _entity_alias_candidates(token)
    if not alias_candidates:
        return None

    best_score = -1
    best_field: Dict[str, Any] | None = None
    for field in top_fields:
        label = str(field.get("label") or "").strip()
        if not label:
            continue
        label_key = _normalize_entity_key(label)
        if not label_key:
            continue
        score = 0
        for token_key in alias_candidates:
            if token_key == label_key:
                score = max(score, 100)
            elif token_key and token_key in label_key:
                score = max(score, 80)
            elif label_key and label_key in token_key:
                score = max(score, 70)
        if score > best_score:
            best_score = score
            best_field = field
    if best_score <= 0:
        return None
    return best_field


def match_frontend_requested_entities(
    *,
    requested_entities: List[str],
    top_fields: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    extracted: List[Dict[str, Any]] = []
    missing: List[str] = []
    used_labels: set[str] = set()

    for token in requested_entities:
        matched = _match_entity_token_to_field(token, top_fields)
        if not isinstance(matched, dict):
            missing.append(token)
            continue
        label = str(matched.get("label") or "").strip()
        if not label or label in used_labels:
            continue
        used_labels.add(label)
        extracted.append(matched)

    return extracted, missing


def build_frontend_entity_extraction_answer(
    *,
    question: str,
    file_name: str,
    top_fields: List[Dict[str, Any]],
) -> str:
    if not is_entity_extraction_question(question):
        return ""
    if not top_fields:
        return ""

    requested_entities = extract_requested_entities(question)
    extracted_fields, missing_entities = match_frontend_requested_entities(
        requested_entities=requested_entities,
        top_fields=top_fields,
    )
    if not extracted_fields:
        if requested_entities:
            return ""
        extracted_fields = _preferred_verification_fields(top_fields, limit=3)

    if wants_json_like_output(question):
        payload = {
            "intent": "entity_extraction",
            "file_name": file_name,
            "requested_entities": requested_entities,
            "extracted": {
                str(field.get("label") or "").strip(): str(field.get("value") or "").strip()
                for field in extracted_fields
                if str(field.get("label") or "").strip() and str(field.get("value") or "").strip()
            },
            "missing": missing_entities,
            "provenance": [
                {
                    "label": str(field.get("label") or "").strip(),
                    "page": field.get("page"),
                    "confidence": field.get("confidence"),
                }
                for field in extracted_fields
                if str(field.get("label") or "").strip()
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    pairs = []
    for field in extracted_fields:
        label = str(field.get("label") or "").strip()
        value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
        if not label or not value:
            continue
        pairs.append(f"{label}：{value}")
    if not pairs:
        return ""
    answer = "；".join(pairs) + "。"
    if missing_entities:
        answer += f" 未在当前快照命中的字段：{'、'.join(missing_entities)}。"
    return answer


def should_short_circuit_with_frontend_snapshot(
    *,
    user_message: str,
    snapshot_answer: str,
    extra_context: Optional[Dict[str, Any]] = None,
) -> bool:
    question = str(user_message or "").strip()
    if not str(snapshot_answer or "").strip():
        return False
    if looks_like_placeholder_answer(snapshot_answer):
        return False
    if is_conditional_row_lookup_question(question):
        lowered_snapshot = str(snapshot_answer or "").lower()
        if (
            "未找到" in snapshot_answer
            or "不唯一" in snapshot_answer
            or "证据" in snapshot_answer
            or "ref_id" in lowered_snapshot
        ):
            return True
        return False
    if is_locked_row_lookup_question(question):
        lowered_snapshot = str(snapshot_answer or "").lower()
        if "证据" in snapshot_answer or "ref_id" in lowered_snapshot:
            return True
        return False
    # Only short-circuit for explicitly terse/minimal requests (e.g. "只回答数字").
    if is_strict_minimal_request(question):
        return True
    if is_document_risk_review_question(question):
        return True
    if is_card_field_selection_question(question):
        return True
    if is_field_provenance_question(question):
        return True
    if is_entity_extraction_question(question):
        return True
    if looks_like_temporal_scope_lookup(question) and not is_broad_document_question(question):
        return True
    if is_summary_with_field_inventory_question(question):
        return _summary_short_circuit_ready(extra_context)
    if is_broad_document_question(question):
        return False
    if looks_like_exact_field_question(question):
        return True
    return False


def looks_like_placeholder_answer(answer: str) -> bool:
    text = str(answer or "").strip()
    if not text:
        return False
    markers = (
        "[company/project/contract/report]",
        "此处填入",
        "示例标题或主旨文本",
        "若文档为合同",
        "若为技术报告",
        "若为发票/票据",
        "文档标题 / 主旨",
        "涉及当事方或作者（甲方/乙方/作者）",
        "字段名：文档标题 / 主旨",
        "当前值：[",
        "文档主要描述了……",
    )
    return any(marker in text for marker in markers)


def extract_frontend_top_fields(raw_fields: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(raw_fields, list):
        return normalized
    for item in raw_fields[:12]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value:
            continue
        confidence_raw = item.get("confidence")
        page_raw = item.get("page")
        normalized.append(
            {
                "label": label,
                "value": value,
                "confidence": int(confidence_raw) if isinstance(confidence_raw, (int, float)) else None,
                "page": int(page_raw) if isinstance(page_raw, (int, float)) else None,
            }
        )
    return normalized


def frontend_field_match_score(question: str, field: Dict[str, Any]) -> int:
    normalized_question = re.sub(r"\s+", "", str(question or ""))
    label = re.sub(r"\s+", "", str(field.get("label") or ""))
    value = re.sub(r"\s+", "", str(field.get("value") or ""))
    if not label:
        return 0
    score = 0
    if label and label in normalized_question:
        score += 12 + len(label)
    if normalized_question and normalized_question in label:
        score += 4
    for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", label):
        token = token.strip()
        if len(token) >= 2 and token in normalized_question:
            score += 3
    if value and len(value) <= 24 and value in normalized_question:
        score += 1
    return score


def match_frontend_fields(question: str, fields: List[Dict[str, Any]], *, limit: int = 4) -> List[Dict[str, Any]]:
    normalized_question = re.sub(r"\s+", "", str(question or ""))
    ranked: List[tuple[int, int, int, Dict[str, Any]]] = []
    for field in fields:
        label = re.sub(r"\s+", "", str(field.get("label") or ""))
        score = frontend_field_match_score(normalized_question, field)
        if not label or score <= 0:
            continue
        position = normalized_question.find(label)
        if position < 0:
            position = 10**6
        ranked.append((position, -score, -len(label), field))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    matched_fields: List[Dict[str, Any]] = []
    seen_labels: set[str] = set()
    for _, _, _, field in ranked:
        label = str(field.get("label") or "").strip()
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        matched_fields.append(field)
        if len(matched_fields) >= max(1, int(limit or 1)):
            break
    return matched_fields


def looks_like_exact_field_question(question: str) -> bool:
    text = str(question or "").strip()
    markers = ("是什么", "是多少", "哪一年", "多少", "数值", "值", "标题", "文件名")
    return any(marker in text for marker in markers)


def is_conditional_row_lookup_question(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    lowered = text.lower()
    asks_value = looks_like_exact_field_question(text) or any(
        marker in text for marker in ("页码", "行号", "ref_id", "表格", "table", "row")
    )
    row_intent = any(
        marker in text
        for marker in ("这一行", "同一行", "该行", "对应行", "定位", "返回", "提取", "查询")
    ) or any(
        marker in lowered
        for marker in ("same row", "this row", "that row", "locate", "return", "extract")
    )
    if not asks_value and not row_intent:
        return False
    chinese_condition = bool(
        re.search(
            r"[\u4e00-\u9fffA-Za-z0-9_]{1,24}\s*(?:为|等于|=|是)\s*[\"'“”《》]?\s*[^，,。；;\"'“”《》]{1,48}",
            text,
        )
    )
    english_condition = (
        bool(re.search(r"\bwhere\b", lowered))
        or bool(re.search(r"\bwhose\b", lowered))
        or bool(re.search(r"\bwith\b", lowered))
    ) and bool(re.search(r"\b(?:is|equals|=)\b", lowered))
    return chinese_condition or english_condition


def _extract_condition_pairs(text: str) -> List[Dict[str, str]]:
    if not text:
        return []

    scopes = [str(item or "").strip() for item in re.findall(r"[\"'“”《》](.{1,180}?)[\"'“”《》]", text)]
    scopes.append(text)

    best_pairs: List[Dict[str, str]] = []
    for scope in scopes:
        if not scope:
            continue
        local_pairs: List[Dict[str, str]] = []
        seen_local = set()
        parts = re.split(r"\s*(?:且|并且|并|and|&|,|，|;|；)\s*", scope, flags=re.IGNORECASE)
        for part in parts:
            segment = str(part or "").strip()
            if not segment:
                continue
            match = re.search(
                r"(?P<field>[\u4e00-\u9fffA-Za-z0-9_./（）()\-]+)\s*(?:为|等于|=|是)\s*(?P<value>.+)$",
                segment,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            field = str(match.group("field") or "").strip(" ：:")
            value = str(match.group("value") or "").strip(" ：:")
            value = re.sub(
                r"(?:这|该|同|当前)?一行(?:记录|数据)?\s*$",
                "",
                value,
            ).strip(" ：:")
            if not field or not value:
                continue
            dedup_key = (_normalize_entity_key(field), _normalize_entity_key(value))
            if not dedup_key[0] or not dedup_key[1] or dedup_key in seen_local:
                continue
            seen_local.add(dedup_key)
            local_pairs.append({"field": field, "value": value})
        if len(local_pairs) > len(best_pairs):
            best_pairs = local_pairs
    return best_pairs


def _extract_conditional_lookup_parts(question: str) -> Dict[str, str]:
    text = str(question or "").strip()
    if not text:
        return {}

    def _clean_target_field(raw_target: str) -> str:
        target = str(raw_target or "").strip()
        if not target:
            return ""
        target = re.sub(
            r"^(?:这|该|同|当前)?一行(?:记录|数据)?[，,、\s]*",
            "",
            target,
        )
        target = re.sub(
            r"^(?:(?:请|并|然后|再)\s*)?(?:返回|给出|输出|提取|查询|查找|定位)\s*",
            "",
            target,
        )
        target = re.sub(r"(?:和|及|并|,|，)?\s*ref[_\s-]?id\b.*$", "", target, flags=re.IGNORECASE)
        target = re.split(r"[？?。!！,，;；\n]", target, maxsplit=1)[0]
        target = re.sub(r"(?:是多少|多少|是什么|是啥|为多少|的值)\s*$", "", target).strip(" ：:")
        return target

    zh_match = re.search(
        r"(?P<condition_field>[\u4e00-\u9fffA-Za-z0-9_./（）()\-]+?)\s*(?:为|等于|=)\s*"
        r"(?P<condition_value>[^，,。；;]{1,40}?)\s*的\s*(?P<rest>.+)$",
        text,
    )
    if zh_match:
        condition_field = str(zh_match.group("condition_field") or "").strip()
        condition_value = str(zh_match.group("condition_value") or "").strip()
        rest = _clean_target_field(str(zh_match.group("rest") or ""))
        has_compound_value = bool(re.search(r"(?:且|并且|\band\b|&)", condition_value, flags=re.IGNORECASE))
        if has_compound_value:
            condition_field = ""
        if condition_field and condition_value and rest:
            return {
                "condition_field": condition_field,
                "condition_value": condition_value,
                "target_field": rest,
            }

    zh_loose = re.search(
        r"(?P<condition_field>[\u4e00-\u9fffA-Za-z0-9_./（）()\-]+?)\s*(?:为|等于|=|是)\s*"
        r"[\"'“”《》]?\s*(?P<condition_value>[^，,。；;\"'“”《》]{1,48})\s*[\"'“”《》]?",
        text,
    )
    if zh_loose:
        condition_field = str(zh_loose.group("condition_field") or "").strip(" ：:")
        condition_value = str(zh_loose.group("condition_value") or "").strip(" ：:")
        condition_value = re.sub(
            r"(?:这|该|同|当前)?一行(?:记录|数据)?\s*$",
            "",
            condition_value,
        ).strip(" ：:")
        has_compound_value = bool(re.search(r"(?:且|并且|\band\b|&)", condition_value, flags=re.IGNORECASE))
        if has_compound_value:
            condition_field = ""

        rest_raw = text[zh_loose.end():] if zh_loose.end() < len(text) else ""
        rest = _clean_target_field(rest_raw)
        if not rest:
            candidates = [
                token
                for token in extract_requested_entities(text)
                if _normalize_entity_key(token) not in {
                    _normalize_entity_key(condition_field),
                    _normalize_entity_key(condition_value),
                    "refid",
                    "ref_id",
                    "行",
                    "row",
                    "table",
                    "表格",
                }
            ]
            if candidates:
                rest = str(candidates[0] or "").strip()
        if condition_field and condition_value and rest:
            return {
                "condition_field": condition_field,
                "condition_value": condition_value,
                "target_field": rest,
            }

    if re.search(r"(?:且|并且|\band\b|&)", text, flags=re.IGNORECASE):
        pairs = _extract_condition_pairs(text)
        if len(pairs) >= 2:
            rest = ""
            quoted_rest_match = re.search(
                r"[\"'“”《》][^\"'“”《》]{1,200}[\"'“”《》]\s*(?P<rest>.+)$",
                text,
            )
            if quoted_rest_match:
                rest = _clean_target_field(str(quoted_rest_match.group("rest") or ""))
            if not rest:
                action_rest_match = re.search(
                    r"(?:返回|给出|输出|提取|查询|查找)\s*(?P<rest>.+)$",
                    text,
                )
                if action_rest_match:
                    rest = _clean_target_field(str(action_rest_match.group("rest") or ""))
            if not rest:
                blocked_tokens = {"refid", "ref_id", "行", "row", "table", "表格"}
                blocked_tokens.update(_normalize_entity_key(item.get("field")) for item in pairs)
                blocked_tokens.update(_normalize_entity_key(item.get("value")) for item in pairs)
                candidates = [
                    token
                    for token in extract_requested_entities(text)
                    if _normalize_entity_key(token) not in blocked_tokens
                ]
                if candidates:
                    rest = str(candidates[0] or "").strip()
            if rest:
                return {
                    "condition_field": str(pairs[0].get("field") or "").strip(),
                    "condition_value": str(pairs[0].get("value") or "").strip(),
                    "target_field": rest,
                    "condition_pairs": [
                        {
                            "field": str(item.get("field") or "").strip(),
                            "value": str(item.get("value") or "").strip(),
                        }
                        for item in pairs
                        if str(item.get("field") or "").strip() and str(item.get("value") or "").strip()
                    ],
                }

    lowered = text.lower()
    en_match = re.search(
        r"\bwhere\s+(?P<condition_field>[a-z0-9_ ]{1,40})\s*(?:=|is|equals)\s*"
        r"(?P<condition_value>[a-z0-9_ .-]{1,40})\b.*?\b(?:(?:what is)|(?:value of))\s+"
        r"(?P<target_field>[a-z0-9_ ]{1,40})",
        lowered,
    )
    if en_match:
        condition_field = str(en_match.group("condition_field") or "").strip()
        condition_value = str(en_match.group("condition_value") or "").strip()
        target_field = str(en_match.group("target_field") or "").strip()
        if condition_field and condition_value and target_field:
            return {
                "condition_field": condition_field,
                "condition_value": condition_value,
                "target_field": target_field,
            }
    return {}


def _match_header_index(headers: List[str], target: str) -> int:
    target_key = _normalize_entity_key(target)
    if not target_key:
        return -1
    best_score = -1
    best_index = -1
    for index, header in enumerate(headers):
        header_key = _normalize_entity_key(header)
        if not header_key:
            continue
        score = 0
        if header_key == target_key:
            score = 100
        elif target_key in header_key:
            score = 80
        elif header_key in target_key:
            score = 70
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score > 0 else -1


def is_locked_row_lookup_question(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    lowered = text.lower()
    row_markers = (
        "刚才那一行",
        "同一行",
        "锁定行",
        "当前行",
        "继续看",
        "same row",
        "locked row",
        "current row",
    )
    value_markers = (
        "值",
        "字段",
        "ref_id",
        "what is",
        "value",
        "field",
    )
    return (
        any(marker in text for marker in row_markers)
        or any(marker in lowered for marker in row_markers)
    ) and (
        any(marker in text for marker in value_markers)
        or any(marker in lowered for marker in value_markers)
    )


def _locked_row_target_candidates(question: str) -> List[str]:
    text = str(question or "").strip()
    lowered = text.lower()
    candidates = extract_requested_entities(text)
    if re.search(r"pm\s*10", lowered):
        candidates.append("pm10")
    if re.search(r"pm\s*2\.?\s*5|pm25", lowered):
        candidates.extend(("pm2.5", "pm25"))
    if ("pollution-type" in lowered) or ("pollution type" in lowered) or ("污染类型" in text):
        candidates.extend(("pollution-type", "污染类型"))
    if ("primary pollutant" in lowered) or ("首要污染物" in text):
        candidates.extend(("primary pollutant", "首要污染物"))

    dedup: List[str] = []
    seen = set()
    for item in candidates:
        normalized = _normalize_entity_key(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        dedup.append(str(item))
    return dedup


def _resolve_locked_row_ref_id(
    *,
    base_ref_id: str,
    table_id: str,
    source_row_index: int,
    row_index: int,
    target_col_index: int,
) -> str:
    col_num = max(1, int(target_col_index) + 1)
    source_row_num = int(source_row_index or 0)
    base = str(base_ref_id or "").strip()
    if base:
        match = re.match(r"^(?P<prefix>.*_r)(?P<row>\d+)_c(?P<col>\d+)$", base)
        if match:
            parsed_row_num = int(match.group("row"))
            row_num = source_row_num if source_row_num > 0 else parsed_row_num
            return f"{match.group('prefix')}{row_num}_c{col_num}"
        return base
    row_num = max(1, int(source_row_index or row_index or 1))
    table_prefix = str(table_id or "table").strip() or "table"
    return f"{table_prefix}_r{row_num}_c{col_num}"


def _pollution_type_like_value(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    if "pm10" in normalized or "pm2.5" in normalized or "pm25" in normalized:
        return False
    keywords = (
        "good",
        "moderate",
        "unhealthy",
        "severe",
        "优",
        "良",
        "轻度污染",
        "中度污染",
        "重度污染",
        "严重污染",
    )
    return any(key in normalized for key in keywords)


def build_frontend_locked_row_lookup_answer(
    *,
    question: str,
    table_row_samples: Any,
    current_locked_object: Any,
) -> str:
    if not is_locked_row_lookup_question(question):
        return ""
    if not isinstance(current_locked_object, dict):
        return ""
    if not isinstance(table_row_samples, list) or len(table_row_samples) == 0:
        return ""

    lock_table_id = str(current_locked_object.get("table_id") or current_locked_object.get("object_id") or "").strip()
    lock_ref_id = str(current_locked_object.get("ref_id") or "").strip()
    lock_row_index = current_locked_object.get("row_index")
    lock_source_row_index = current_locked_object.get("source_row_index")
    lock_row_index = int(lock_row_index) if isinstance(lock_row_index, (int, float)) else None
    lock_source_row_index = int(lock_source_row_index) if isinstance(lock_source_row_index, (int, float)) else None

    target_candidates = _locked_row_target_candidates(question)
    if not target_candidates:
        return ""

    lowered_question = str(question or "").lower()
    wants_pollution_type = (
        ("pollution-type" in lowered_question)
        or ("pollution type" in lowered_question)
        or ("污染类型" in str(question or ""))
    )

    for sample in table_row_samples[:8]:
        if not isinstance(sample, dict):
            continue
        sample_table_id = str(sample.get("table_id") or "").strip()
        if lock_table_id and sample_table_id and sample_table_id != lock_table_id:
            continue

        headers = [str(item or "").strip() for item in sample.get("headers", []) if str(item or "").strip()]
        rows_raw = sample.get("rows")
        if not headers or not isinstance(rows_raw, list) or len(rows_raw) == 0:
            continue

        chosen_row: Optional[Dict[str, Any]] = None
        for row_pos, row_item in enumerate(rows_raw[:120], start=1):
            if not isinstance(row_item, dict):
                continue
            row_index_raw = row_item.get("row_index")
            source_row_index_raw = row_item.get("source_row_index")
            row_index = int(row_index_raw) if isinstance(row_index_raw, (int, float)) else row_pos
            source_row_index = (
                int(source_row_index_raw)
                if isinstance(source_row_index_raw, (int, float))
                else row_index
            )
            if lock_source_row_index is not None and source_row_index == lock_source_row_index:
                chosen_row = {
                    "cells": row_item.get("cells"),
                    "row_index": row_index,
                    "source_row_index": source_row_index,
                }
                break
            if lock_row_index is not None and row_index == lock_row_index:
                chosen_row = {
                    "cells": row_item.get("cells"),
                    "row_index": row_index,
                    "source_row_index": source_row_index,
                }
                break

        if not chosen_row and len(rows_raw) == 1 and isinstance(rows_raw[0], dict):
            single = rows_raw[0]
            row_index_raw = single.get("row_index")
            source_row_index_raw = single.get("source_row_index")
            chosen_row = {
                "cells": single.get("cells"),
                "row_index": int(row_index_raw) if isinstance(row_index_raw, (int, float)) else 1,
                "source_row_index": int(source_row_index_raw) if isinstance(source_row_index_raw, (int, float)) else 1,
            }

        if not chosen_row:
            continue

        cells_raw = chosen_row.get("cells")
        if not isinstance(cells_raw, list) or len(cells_raw) == 0:
            continue
        cells = [str(item or "").strip() for item in cells_raw]

        target_col_index = -1
        for candidate in target_candidates:
            index = _match_header_index(headers, candidate)
            if index >= 0:
                target_col_index = index
                break

        if target_col_index < 0 and wants_pollution_type:
            for index, value in enumerate(cells[:-1]):
                value_key = _normalize_entity_key(value)
                if not value_key:
                    continue
                if "pm10" in value_key or "pm25" in value_key or "颗粒物" in value:
                    next_value = str(cells[index + 1] or "").strip()
                    if next_value and len(next_value) <= 12:
                        target_col_index = index + 1
                        break
            if target_col_index < 0:
                for index, value in enumerate(cells):
                    if _pollution_type_like_value(value):
                        target_col_index = index
                        break

        if target_col_index < 0 or target_col_index >= len(cells):
            continue

        target_value = str(cells[target_col_index] or "").strip()
        if not target_value:
            continue

        field_label = (
            str(headers[target_col_index] or "").strip()
            if target_col_index < len(headers)
            else str(target_candidates[0] or "field").strip()
        )
        row_index_value = int(chosen_row.get("row_index") or 1)
        source_row_index_value = int(chosen_row.get("source_row_index") or row_index_value)
        resolved_ref_id = _resolve_locked_row_ref_id(
            base_ref_id=lock_ref_id or str(sample.get("ref_id") or "").strip(),
            table_id=sample_table_id or lock_table_id or "table",
            source_row_index=source_row_index_value,
            row_index=row_index_value,
            target_col_index=target_col_index,
        )
        return (
            f"{field_label}={target_value}。"
            f"证据：table_id={sample_table_id or lock_table_id or 'N/A'}, page={sample.get('page')}, "
            f"row_index={row_index_value}, source_row_index={source_row_index_value}, ref_id={resolved_ref_id}。"
        )

    return ""


def build_frontend_conditional_lookup_answer(
    *,
    question: str,
    table_row_samples: Any,
) -> str:
    if not is_conditional_row_lookup_question(question):
        return ""
    parts = _extract_conditional_lookup_parts(question)
    if not parts:
        return ""
    if not isinstance(table_row_samples, list) or len(table_row_samples) == 0:
        return (
            f"当前快照未包含可核验的行级表格证据，无法确认“{parts['condition_field']}={parts['condition_value']}”对应的"
            f"{parts['target_field']}。请先提供可定位到页码/行号/ref_id 的表格证据。"
        )

    condition_pairs_raw = parts.get("condition_pairs")
    condition_pairs: List[Dict[str, str]] = []
    if isinstance(condition_pairs_raw, list):
        for item in condition_pairs_raw:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            value = str(item.get("value") or "").strip()
            if not field or not value:
                continue
            condition_pairs.append({"field": field, "value": value})
    if not condition_pairs:
        condition_field = str(parts.get("condition_field") or "").strip()
        condition_value = str(parts.get("condition_value") or "").strip()
        if not condition_field or not condition_value:
            return ""
        condition_pairs = [{"field": condition_field, "value": condition_value}]

    target_field = parts["target_field"]
    condition_descriptions: List[str] = []
    for pair in condition_pairs:
        normalized_value = _normalize_entity_key(pair["value"])
        if not normalized_value:
            return ""
        condition_descriptions.append(f"{pair['field']}={pair['value']}")
    condition_text = " 且 ".join(condition_descriptions)

    matches: List[Dict[str, Any]] = []
    for sample in table_row_samples[:6]:
        if not isinstance(sample, dict):
            continue
        headers = [str(item or "").strip() for item in sample.get("headers", []) if str(item or "").strip()]
        if not headers:
            continue
        target_col_index = _match_header_index(headers, target_field)
        if target_col_index < 0:
            continue
        condition_slots: List[Dict[str, Any]] = []
        for pair in condition_pairs:
            condition_col_index = _match_header_index(headers, pair["field"])
            if condition_col_index < 0:
                condition_slots = []
                break
            condition_slots.append(
                {
                    "field": pair["field"],
                    "value": pair["value"],
                    "value_key": _normalize_entity_key(pair["value"]),
                    "col_index": condition_col_index,
                }
            )
        if not condition_slots:
            continue

        rows_raw = sample.get("rows")
        if not isinstance(rows_raw, list):
            continue
        for row_pos, row_item in enumerate(rows_raw[:60], start=1):
            row_cells: List[str] = []
            row_index = row_pos
            source_row_index = row_pos
            row_ref_id = ""
            if isinstance(row_item, dict):
                cells_value = row_item.get("cells")
                if isinstance(cells_value, list):
                    row_cells = [str(cell or "").strip() for cell in cells_value]
                row_index_raw = row_item.get("row_index")
                if isinstance(row_index_raw, (int, float)):
                    row_index = max(1, int(row_index_raw))
                source_row_index_raw = row_item.get("source_row_index")
                if isinstance(source_row_index_raw, (int, float)):
                    source_row_index = max(1, int(source_row_index_raw))
                else:
                    source_row_index = row_index
                row_ref_id = str(row_item.get("ref_id") or "").strip()
            elif isinstance(row_item, list):
                row_cells = [str(cell or "").strip() for cell in row_item]
                source_row_index = row_index
            if not row_cells:
                continue

            matched_conditions: List[Dict[str, str]] = []
            slot_mismatch = False
            for slot in condition_slots:
                condition_cell = row_cells[slot["col_index"]] if slot["col_index"] < len(row_cells) else ""
                condition_cell_key = _normalize_entity_key(condition_cell)
                if not condition_cell_key:
                    slot_mismatch = True
                    break
                value_key = str(slot["value_key"] or "").strip()
                if value_key not in condition_cell_key and condition_cell_key not in value_key:
                    slot_mismatch = True
                    break
                matched_conditions.append(
                    {
                        "field": str(slot["field"] or "").strip(),
                        "value": str(slot["value"] or "").strip(),
                        "cell": condition_cell,
                    }
                )
            if slot_mismatch:
                continue

            target_value = row_cells[target_col_index] if target_col_index < len(row_cells) else ""
            matches.append(
                {
                    "target_value": str(target_value or "").strip(),
                    "table_id": str(sample.get("table_id") or "").strip(),
                    "table_ref_id": str(sample.get("ref_id") or "").strip(),
                    "row_ref_id": row_ref_id,
                    "page": sample.get("page"),
                    "row_index": row_index,
                    "source_row_index": source_row_index,
                    "target_col_index": target_col_index,
                    "matched_conditions": matched_conditions,
                }
            )

    if not matches:
        return (
            f"在当前可见表格证据中未找到“{condition_text}”的记录，"
            f"暂时无法给出 {target_field}。请补充可定位到页码/行号/ref_id 的证据。"
        )

    if len(matches) > 1:
        preview_items = []
        for item in matches[:3]:
            preview_ref_id = _resolve_locked_row_ref_id(
                base_ref_id=str(item.get("row_ref_id") or item.get("table_ref_id") or "").strip(),
                table_id=str(item.get("table_id") or "table").strip() or "table",
                source_row_index=int(item.get("source_row_index") or item.get("row_index") or 1),
                row_index=int(item.get("row_index") or 1),
                target_col_index=int(item.get("target_col_index") or 0),
            )
            preview_items.append(
                f"page={item.get('page')}, row_index={item.get('row_index')}, ref_id={preview_ref_id or 'N/A'}"
            )
        preview_text = "; ".join(preview_items)
        return (
            f"命中结果不唯一：当前找到 {len(matches)} 条“{condition_text}”记录，"
            f"无法唯一确定 {target_field}。候选证据：{preview_text}。"
        )

    match = matches[0]
    target_value = str(match.get("target_value") or "").strip()
    resolved_ref_id = _resolve_locked_row_ref_id(
        base_ref_id=str(match.get("row_ref_id") or match.get("table_ref_id") or "").strip(),
        table_id=str(match.get("table_id") or "table").strip() or "table",
        source_row_index=int(match.get("source_row_index") or match.get("row_index") or 1),
        row_index=int(match.get("row_index") or 1),
        target_col_index=int(match.get("target_col_index") or 0),
    )
    if not target_value:
        return (
            f"已定位到“{condition_text}”对应行，但 {target_field} 为空值。"
            f"证据：page={match.get('page')}, row_index={match.get('row_index')}, "
            f"source_row_index={match.get('source_row_index')}, ref_id={resolved_ref_id or 'N/A'}。"
        )

    return (
        f"{target_field}={target_value}。"
        f"证据：table_id={match.get('table_id') or 'N/A'}, page={match.get('page')}, "
        f"row_index={match.get('row_index')}, source_row_index={match.get('source_row_index')}, "
        f"ref_id={resolved_ref_id or 'N/A'}。"
    )


def is_card_field_selection_question(question: str) -> bool:
    text = str(question or "").strip()
    lowered = text.lower()
    markers = (
        "首页卡片",
        "首屏卡片",
        "保留两个字段",
        "保留哪两个字段",
        "留哪两个字段",
        "只保留两个",
        "最稳妥的字段",
        "dashboard card",
        "card field",
        "key field pair",
        "two fields",
        "2 fields",
        "pick two fields",
    )
    return (
        any(marker in text for marker in markers)
        or any(marker in lowered for marker in markers)
        or (("卡片" in text or "card" in lowered) and ("字段" in text or "field" in lowered))
    )


def is_field_provenance_question(question: str) -> bool:
    text = str(question or "").strip()
    lowered = text.lower()
    markers = (
        "来自文档里的哪一类信息",
        "来自哪一类信息",
        "属于哪一类信息",
        "这个数字来自哪里",
        "这个数值来自哪里",
        "来源是什么",
        "证据来源",
        "出处是什么",
        "字段来源",
        "source of this value",
        "where does this number come from",
        "provenance",
        "evidence source",
    )
    return any(marker in text for marker in markers) or any(marker in lowered for marker in markers)


def looks_like_temporal_scope_lookup(question: str) -> bool:
    text = str(question or "").strip()
    if re.search(r"20\d{2}", text):
        return True
    if re.search(r"(?:第?[一二三四1234]\s*季(?:度)?|Q[1-4]|quarter)", text, flags=re.IGNORECASE):
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in ("季度", "q1", "q2", "q3", "q4", "season"))


def format_frontend_field_value(question: str, field: Dict[str, Any]) -> str:
    value = str(field.get("value") or "").strip()
    if not value:
        return ""
    if "只回答数字" in str(question or ""):
        numeric = re.search(r"[-+]?\d+(?:\.\d+)?", value)
        if numeric:
            return numeric.group(0)
    return value


def format_frontend_field_answer(field: Dict[str, Any]) -> str:
    label = str(field.get("label") or "").strip() or "字段"
    value = str(field.get("value") or "").strip() or "暂无可用值"
    return f"{label}是 {value}。"


def _pick_primary_frontend_field(question: str, matched_fields: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not matched_fields:
        return None
    normalized_question = re.sub(r"\s+", "", str(question or ""))
    penalty_markers = ("统计年份", "年份", "时间", "日期", "页码", "来源")
    ranked: List[tuple[int, int, Dict[str, Any]]] = []
    for index, field in enumerate(matched_fields):
        label = str(field.get("label") or "").strip()
        if not label:
            continue
        score = frontend_field_match_score(normalized_question, field)
        if any(marker in label for marker in penalty_markers):
            score -= 6
        if len(label) >= 4:
            score += 1
        ranked.append((score, -index, field))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def looks_like_extraction_style_summary(summary: str) -> bool:
    text = re.sub(r"\s+", " ", str(summary or "")).strip()
    if not text:
        return False
    markers = (
        "已完成内容解析",
        "已抽取的关键信息包括",
        "从原文与溯源片段看",
        "当前解析结果看",
        "表格内容主要围绕",
        "图表部分重点提到了",
        "已抽取",
        "溯源片段",
    )
    return any(marker in text for marker in markers)


def _topic_labels_from_fields(top_fields: List[Dict[str, Any]]) -> List[str]:
    labels = [str(field.get("label") or "").strip() for field in top_fields if str(field.get("label") or "").strip()]
    joined = " ".join(labels)
    topics: List[str] = []
    topic_rules = (
        (("生产总值", "增加值", "工业"), "经济总量"),
        (("人口", "城镇化", "自然增长率"), "人口结构"),
        (("就业",), "就业"),
        (("消费", "零售"), "消费"),
        (("进出口",), "进出口"),
        (("预算", "财政"), "财政收支"),
        (("价格", "CPI"), "价格变化"),
    )
    for markers, topic in topic_rules:
        if any(marker in joined for marker in markers) and topic not in topics:
            topics.append(topic)
    return topics[:5]


def _preferred_summary_fields(top_fields: List[Dict[str, Any]], *, limit: int = 2) -> List[Dict[str, Any]]:
    generic_labels = {
        "绝对值",
        "统计年份",
        "比上年末增长",
        "自然增长率",
    }
    ranked: List[tuple[int, Dict[str, Any]]] = []
    for field in top_fields:
        label = str(field.get("label") or "").strip()
        value = str(field.get("value") or "").strip()
        if not label or not value:
            continue
        score = 0
        if label in generic_labels:
            score -= 8
        if any(marker in label for marker in ("生产总值", "人口", "预算", "收入", "消费", "进出口", "就业")):
            score += 6
        if label == "常住人口":
            score += 2
        if "城镇化率" in label or label.endswith("增长率"):
            score -= 2
        if len(label) >= 4:
            score += 1
        ranked.append((score, field))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected: List[Dict[str, Any]] = []
    seen_labels: set[str] = set()
    for _, field in ranked:
        label = str(field.get("label") or "").strip()
        if label in seen_labels:
            continue
        seen_labels.add(label)
        selected.append(field)
        if len(selected) >= max(1, int(limit or 1)):
            break
    return selected


def _find_frontend_field_by_label(top_fields: List[Dict[str, Any]], markers: tuple[str, ...]) -> Dict[str, Any] | None:
    for field in top_fields:
        label = str(field.get("label") or "").strip()
        if label and any(marker in label for marker in markers):
            return field
    return None


def _preferred_verification_fields(top_fields: List[Dict[str, Any]], *, limit: int = 2) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    excluded_markers = ("统计年份", "年份", "时间", "日期", "页码", "来源", "标题", "文件名")
    for field in top_fields:
        label = str(field.get("label") or "").strip()
        value = str(field.get("value") or "").strip()
        if not label or not value:
            continue
        if any(marker in label for marker in excluded_markers):
            continue
        filtered.append(field)
        if len(filtered) >= max(1, int(limit or 1)):
            break
    if filtered:
        return filtered
    return _preferred_summary_fields(top_fields, limit=limit)


def _collect_time_hints(
    *,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> tuple[List[str], bool]:
    text_parts = [file_name, summary]
    text_parts.extend(str(field.get("label") or "").strip() for field in top_fields)
    text_parts.extend(str(field.get("value") or "").strip() for field in top_fields)
    text_parts.extend(table_column_headers)
    text_parts.extend(figure_key_points)
    combined = " ".join(part for part in text_parts if str(part or "").strip())
    years = sorted(set(re.findall(r"20\d{2}", combined)))
    has_quarter = bool(re.search(r"(?:第?[一二三四1234]\s*季度|Q[1-4]|quarter)", combined, flags=re.IGNORECASE))
    return years, has_quarter


def _derive_document_opening(
    *,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
) -> str:
    normalized_summary = re.sub(r"\s+", " ", str(summary or "")).strip()
    normalized_file_name = str(file_name or "").strip()
    title_without_ext = re.sub(r"\.[A-Za-z0-9]+$", "", normalized_file_name)
    year_hits = sorted(set(re.findall(r"20\d{2}", title_without_ext)))
    year_scope = ""
    if len(year_hits) >= 2:
        year_scope = f"{year_hits[0]} 到 {year_hits[-1]}"
    elif len(year_hits) == 1:
        year_scope = year_hits[0]
    topics = _topic_labels_from_fields(top_fields)

    if normalized_summary and not looks_like_extraction_style_summary(normalized_summary):
        if normalized_file_name and f"《{normalized_file_name}》" not in normalized_summary and normalized_file_name not in normalized_summary:
            return f"这份文档《{normalized_file_name}》主要在讲：{normalized_summary}"
        return normalized_summary

    if normalized_file_name and ("统计公报" in normalized_file_name or "国民经济" in normalized_file_name):
        if year_scope and topics:
            return f"这份文档更像是一份围绕 {year_scope} 年度情况整理的统计公报汇总，主要在梳理{ '、'.join(topics) }等核心指标。"
        if topics:
            return f"这份文档是一份统计公报类材料，重点在梳理{ '、'.join(topics) }等核心指标。"
        return f"这份文档是一份统计公报类材料，核心是在按年份汇总主要发展指标。"

    if topics:
        if normalized_file_name:
            return f"当前这份文档《{normalized_file_name}》主要围绕{ '、'.join(topics) }等内容展开。"
        return f"当前文档主要围绕{ '、'.join(topics) }等内容展开。"

    if normalized_file_name:
        return f"当前这份文档《{normalized_file_name}》已经完成解析。"
    return "当前文档已经完成解析。"


def build_frontend_summary_paragraph(
    *,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> str:
    normalized_sentences: List[str] = []
    opening = _derive_document_opening(
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
    )
    if opening:
        normalized_sentences.append(opening)

    stable_pairs_normalized: List[str] = []
    for field in _preferred_summary_fields(top_fields, limit=2):
        label = str(field.get("label") or "").strip()
        value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
        if not label or not value:
            continue
        stable_pairs_normalized.append(f"{label}是{value}")
    if stable_pairs_normalized:
        normalized_sentences.append("最关键的字段包括" + "、".join(stable_pairs_normalized) + "。")

    column_preview_normalized = "、".join(
        [str(item).strip() for item in table_column_headers[:5] if str(item).strip()]
    )
    if column_preview_normalized:
        normalized_sentences.append(f"表格内容主要围绕 {column_preview_normalized} 这些维度展开。")

    point_preview_normalized = "；".join(
        [str(item).strip() for item in figure_key_points[:2] if str(item).strip()]
    )
    if point_preview_normalized:
        normalized_sentences.append(f"图表部分重点提到：{point_preview_normalized}。")

    return " ".join(sentence for sentence in normalized_sentences if sentence.strip()).strip()

    sentences: List[str] = []
    opening = _derive_document_opening(
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
    )
    if opening:
        sentences.append(opening)

    stable_pairs = [
        f"{str(field.get('label') or '').strip()}是 {str(field.get('value') or '').strip()}"
        for field in _preferred_summary_fields(top_fields, limit=2)
        if str(field.get("label") or "").strip() and str(field.get("value") or "").strip()
    ]
    stable_pairs = [
        re.sub(r"\s*是\s*", "是", str(item or "").strip())
        for item in stable_pairs
        if str(item or "").strip()
    ]
    if stable_pairs:
        sentences.append("从当前解析结果看，已经比较稳定的关键信息包括" + "，".join(stable_pairs) + "。")

    column_preview = "、".join([str(item).strip() for item in table_column_headers[:5] if str(item).strip()])
    if column_preview:
        sentences.append(f"表格内容主要围绕 {column_preview} 这些维度展开。")

    point_preview = "；".join([str(item).strip() for item in figure_key_points[:2] if str(item).strip()])
    if point_preview:
        sentences.append(f"图表部分重点提到了{point_preview}。")

    return " ".join(sentence for sentence in sentences if sentence.strip()).strip()


def build_frontend_core_summary_answer(
    *,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> str:
    summary_line = build_frontend_summary_paragraph(
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
        table_column_headers=table_column_headers,
        figure_key_points=figure_key_points,
    )
    if not summary_line:
        fallback_name = str(file_name or "").strip()
        summary_line = f"当前文档《{fallback_name}》已完成解析。" if fallback_name else "当前文档已完成解析。"

    lines = [f"当前选中文档的核心内容：{summary_line}"]
    if top_fields:
        lines.append("当前最确定的3个字段：")
        for field in top_fields[:3]:
            label = str(field.get("label") or "").strip()
            value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
            if not label or not value:
                continue
            lines.append(f"{label}：{value}")
    return "\n".join(line for line in lines if str(line or "").strip()).strip()


def build_frontend_risk_review_answer(
    *,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> str:
    del file_name, summary
    lines = ["如果你是第一次核对这份文档，我建议先优先看这 3 类信息："]

    year_field = _find_frontend_field_by_label(top_fields, ("统计年份", "年份", "年度", "时间"))
    if year_field:
        year_label = str(year_field.get("label") or "").strip() or "统计年份"
        year_value = re.sub(r"\s+", " ", str(year_field.get("value") or "")).strip()
        lines.append(
            f"1. 时间与统计口径：先确认{year_label}是否锁定为 {year_value}，并核对这份文档谈的是哪一年度、哪类对象、采用什么统计口径，避免把不同年份或不同口径混在一起。"
        )
    else:
        lines.append(
            "1. 时间与统计口径：先确认这份文档谈的是哪个年份、哪类对象、采用什么统计口径，避免把不同年份或不同统计范围混在一起。"
        )

    key_fields = _preferred_verification_fields(top_fields, limit=2)
    if key_fields:
        field_preview_parts: List[str] = []
        for field in key_fields:
            label = str(field.get("label") or "").strip()
            value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
            if not label or not value:
                continue
            field_preview_parts.append(f"{label}={value}")
        field_preview = "、".join(field_preview_parts)
        if field_preview:
            lines.append(
                f"2. 核心总量字段：优先复核 {field_preview} 这类核心字段，确认数字、单位和对应对象没有串位，这些字段通常最容易被拿去做摘要、卡片或后续比对。"
            )
        else:
            lines.append(
                "2. 核心总量字段：优先复核文档里最核心的总量字段，确认数字、单位和对应对象没有串位。"
            )
    else:
        lines.append(
            "2. 核心总量字段：优先复核文档里最核心的总量字段，确认数字、单位和对应对象没有串位。"
        )

    evidence_bits: List[str] = []
    if table_column_headers:
        evidence_bits.append(f"当前表格维度里已经出现了“{'、'.join(table_column_headers[:4])}”")
    if figure_key_points:
        evidence_bits.append(f"图表重点提到“{'；'.join(figure_key_points[:2])}”")
    evidence_tail = ""
    if evidence_bits:
        evidence_tail = " 当前可见线索里，" + "；".join(evidence_bits) + "。"
    lines.append(
        "3. 表格与图表对应关系：再核对表头、单位、同比或变化口径，以及图表结论和正文描述是否一致，避免列错位、单位误读或把趋势结论读反。"
        + evidence_tail
    )
    return "\n".join(lines)


def build_frontend_card_field_selection_answer(*, top_fields: List[Dict[str, Any]]) -> str:
    year_field = _find_frontend_field_by_label(top_fields, ("统计年份", "年份", "年度", "时间"))
    core_fields = _preferred_verification_fields(top_fields, limit=2)
    if year_field and core_fields:
        primary_core = core_fields[0]
        primary_label = str(primary_core.get("label") or "").strip()
        primary_value = re.sub(r"\s+", " ", str(primary_core.get("value") or "")).strip()
        lines = [
            "如果首页只能保留两个最稳妥的字段，我建议优先保留这两个：",
            f"1. {str(year_field.get('label') or '').strip()}：{str(year_field.get('value') or '').strip()}。这个字段先把时间范围锁定，避免后续引用时口径漂移。",
            f"2. {primary_label}：{primary_value}。这是当前快照里最稳定、辨识度也比较高的核心总量字段。",
        ]
        if len(core_fields) > 1:
            alternative = core_fields[1]
            alt_label = str(alternative.get("label") or "").strip()
            alt_value = re.sub(r"\s+", " ", str(alternative.get("value") or "")).strip()
            if alt_label and alt_value:
                lines.append(f"如果你更想突出服务承载或资源规模，第二个也可以换成 {alt_label}={alt_value}。")
        return "\n".join(lines)

    selected = _preferred_summary_fields(top_fields, limit=2)
    if not selected:
        return ""
    lines = ["如果首页只能保留两个最稳妥的字段，我建议优先保留这两个："]
    for index, field in enumerate(selected, start=1):
        label = str(field.get("label") or "").strip()
        value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
        if not label or not value:
            continue
        lines.append(f"{index}. {label}：{value}。")
    return "\n".join(lines)


def build_frontend_field_provenance_answer(
    *,
    question: str,
    matched_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> str:
    primary_field = _pick_primary_frontend_field(question, matched_fields) or (matched_fields[0] if matched_fields else None)
    if not isinstance(primary_field, dict):
        return ""
    label = str(primary_field.get("label") or "").strip()
    value = re.sub(r"\s+", " ", str(primary_field.get("value") or "")).strip()
    if not label or not value:
        return ""

    hints: List[str] = []
    if table_column_headers:
        hints.append(f"当前可见表格维度是“{'、'.join(table_column_headers[:4])}”")
    if figure_key_points:
        hints.append(f"图表里重点提到了“{'；'.join(figure_key_points[:2])}”")
    hint_text = f" { '；'.join(hints) }。" if hints else ""
    return (
        f"就当前文档快照看，{label}={value} 这个数字来自文档里已经抽取出来的关键统计字段/指标项，不是外部补推。"
        f"如果你问“它属于哪一类信息”，我会把它归到统计指标或数量类信息。{hint_text}"
    ).strip()


def build_frontend_temporal_gap_answer(
    *,
    question: str,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    table_column_headers: List[str],
    figure_key_points: List[str],
) -> str:
    requested_years = sorted(set(re.findall(r"20\d{2}", str(question or ""))))
    requested_quarter = bool(
        re.search(r"(?:第?[一二三四1234]\s*季度|Q[1-4]|quarter)", str(question or ""), flags=re.IGNORECASE)
    )
    available_years, has_quarter = _collect_time_hints(
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
        table_column_headers=table_column_headers,
        figure_key_points=figure_key_points,
    )

    missing_years = [year for year in requested_years if year not in available_years]
    if missing_years and available_years:
        available_label = "、".join(available_years)
        return (
            f"当前这份文档里没有直接给出 {missing_years[0]} 年的数据依据。"
            f"就现在可见的文档快照来看，它只明确覆盖 {available_label} 年相关内容，所以我不能直接给出 {missing_years[0]} 年的数值。"
        )

    if requested_quarter and not has_quarter:
        return (
            "当前这份文档快照里没有看到明确的季度级信息，也没有找到对应季度字段或季度统计口径，"
            "所以我不能直接给出你问的季度数值。"
        )
    return ""


def format_frontend_multi_field_answer(
    *,
    question: str,
    file_name: str,
    summary: str,
    top_fields: List[Dict[str, Any]],
    matched_fields: List[Dict[str, Any]],
) -> str:
    if not matched_fields:
        return ""

    primary_field_normalized = _pick_primary_frontend_field(question, matched_fields)
    if (
        primary_field_normalized
        and looks_like_exact_field_question(question)
        and not is_broad_document_question(question)
    ):
        if is_strict_minimal_request(question):
            return format_frontend_field_value(question, primary_field_normalized)
        return format_frontend_field_answer(primary_field_normalized)

    direct_pairs_normalized: List[str] = []
    for field in matched_fields:
        label = str(field.get("label") or "").strip()
        value = re.sub(r"\s+", " ", str(field.get("value") or "")).strip()
        if not label or not value:
            continue
        direct_pairs_normalized.append(f"{label}是{value}")
    if not direct_pairs_normalized:
        return ""

    question_text = str(question or "").strip()
    if is_broad_document_question(question_text) or "字段" in question_text:
        intro = build_frontend_summary_paragraph(
            file_name=file_name,
            summary=summary,
            top_fields=top_fields,
            table_column_headers=[],
            figure_key_points=[],
        )
        followup = "你这次问到的字段里，" + "；".join(direct_pairs_normalized) + "。"
        return " ".join(part for part in (intro, followup) if part.strip()).strip()

    return "；".join(direct_pairs_normalized) + "。"


def build_frontend_snapshot_answer(*, user_message: str, extra_context: Optional[Dict[str, Any]]) -> str:
    compact = normalize_frontend_context(extra_context)
    if not compact:
        return ""
    current_document = compact.get("current_document") if isinstance(compact.get("current_document"), dict) else {}
    if not current_document:
        return ""

    summary = trim_text(current_document.get("summary"), 800)
    file_name = trim_text(current_document.get("file_name"), 200)
    top_fields = extract_frontend_top_fields(current_document.get("top_fields"))
    table_column_headers = (
        [str(item).strip() for item in current_document.get("table_column_headers", [])[:8] if str(item or "").strip()]
        if isinstance(current_document.get("table_column_headers"), list)
        else []
    )
    figure_key_points = (
        [str(item).strip() for item in current_document.get("figure_key_points", [])[:4] if str(item or "").strip()]
        if isinstance(current_document.get("figure_key_points"), list)
        else []
    )
    table_row_samples = (
        current_document.get("table_row_samples")
        if isinstance(current_document.get("table_row_samples"), list)
        else []
    )
    if not table_row_samples:
        table_row_samples = _build_table_row_samples_from_xlsx_manifest(current_document)
    current_locked_object = (
        current_document.get("current_locked_object")
        if isinstance(current_document.get("current_locked_object"), dict)
        else {}
    )
    question = str(user_message or "").strip()

    locked_row_lookup_answer = build_frontend_locked_row_lookup_answer(
        question=question,
        table_row_samples=table_row_samples,
        current_locked_object=current_locked_object,
    )
    if locked_row_lookup_answer:
        return locked_row_lookup_answer

    conditional_lookup_answer = build_frontend_conditional_lookup_answer(
        question=question,
        table_row_samples=table_row_samples,
    )
    if conditional_lookup_answer:
        return conditional_lookup_answer

    temporal_gap_answer = build_frontend_temporal_gap_answer(
        question=question,
        file_name=file_name,
        summary=summary,
        top_fields=top_fields,
        table_column_headers=table_column_headers,
        figure_key_points=figure_key_points,
    )
    if temporal_gap_answer:
        return temporal_gap_answer

    if is_document_risk_review_question(question):
        return build_frontend_risk_review_answer(
            file_name=file_name,
            summary=summary,
            top_fields=top_fields,
            table_column_headers=table_column_headers,
            figure_key_points=figure_key_points,
        )

    if is_card_field_selection_question(question):
        return build_frontend_card_field_selection_answer(top_fields=top_fields)

    extraction_answer = build_frontend_entity_extraction_answer(
        question=question,
        file_name=file_name,
        top_fields=top_fields,
    )
    if extraction_answer:
        return extraction_answer

    conditional_row_lookup = is_conditional_row_lookup_question(question)
    matched_fields = match_frontend_fields(question, top_fields)
    matched_field = matched_fields[0] if matched_fields else None
    if is_field_provenance_question(question) and matched_fields:
        return build_frontend_field_provenance_answer(
            question=question,
            matched_fields=matched_fields,
            table_column_headers=table_column_headers,
            figure_key_points=figure_key_points,
        )
    if len(matched_fields) >= 2 and not conditional_row_lookup:
        return format_frontend_multi_field_answer(
            question=question,
            file_name=file_name,
            summary=summary,
            top_fields=top_fields,
            matched_fields=matched_fields,
        )
    if matched_field and looks_like_exact_field_question(question) and not conditional_row_lookup:
        if is_strict_minimal_request(question):
            return format_frontend_field_value(question, matched_field)
        return format_frontend_field_answer(matched_field)

    if matched_field and should_short_circuit_with_frontend_snapshot(
        user_message=question,
        snapshot_answer=matched_field.get("value", ""),
    ):
        return format_frontend_field_value(question, matched_field)

    if is_broad_document_question(question) or "字段" in question:
        return build_frontend_core_summary_answer(
            file_name=file_name,
            summary=summary,
            top_fields=top_fields,
            table_column_headers=table_column_headers,
            figure_key_points=figure_key_points,
        )

    return ""


def _build_table_row_samples_from_xlsx_manifest(current_document: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(current_document, dict):
        return []
    diagnostics = (
        current_document.get("diagnostics")
        if isinstance(current_document.get("diagnostics"), dict)
        else {}
    )
    manifest_path = str(
        current_document.get("xlsx_workbook_manifest_path")
        or diagnostics.get("xlsx_workbook_manifest_path")
        or ""
    ).strip()
    if not manifest_path:
        return []

    manifest = load_xlsx_workbook_manifest(manifest_path)
    sheets = manifest.get("sheets") if isinstance(manifest, dict) else []
    if not isinstance(sheets, list) or len(sheets) == 0:
        return []

    samples: List[Dict[str, Any]] = []
    for sheet in sheets[:3]:
        if not isinstance(sheet, dict):
            continue
        rows_artifact_path = str(sheet.get("rows_artifact_path") or "").strip()
        if not rows_artifact_path:
            continue

        payload = load_xlsx_sheet_rows_artifact(rows_artifact_path)
        headers = payload.get("headers") if isinstance(payload, dict) else []
        rows_raw = payload.get("rows") if isinstance(payload, dict) else []
        if not isinstance(headers, list) or not isinstance(rows_raw, list):
            continue
        if len(headers) == 0 or len(rows_raw) == 0:
            continue

        normalized_headers = [str(item or "").strip() for item in headers if str(item or "").strip()]
        if not normalized_headers:
            continue

        sample_rows: List[Dict[str, Any]] = []
        for row in rows_raw[:100]:
            if not isinstance(row, dict):
                continue
            row_index_raw = row.get("row_index")
            source_row_index_raw = row.get("source_row_index")
            row_index = int(row_index_raw) if isinstance(row_index_raw, (int, float)) else 0
            source_row_index = (
                int(source_row_index_raw) if isinstance(source_row_index_raw, (int, float)) else row_index
            )
            cells_raw = row.get("cells")
            if not isinstance(cells_raw, list) or len(cells_raw) == 0:
                continue

            row_cells = [""] * max(1, len(normalized_headers))
            row_ref_id = ""
            for cell in cells_raw:
                if not isinstance(cell, dict):
                    continue
                col_index_raw = cell.get("col_index")
                if not isinstance(col_index_raw, (int, float)):
                    continue
                col_index = int(col_index_raw)
                if col_index <= 0:
                    continue
                if col_index > len(row_cells):
                    row_cells.extend([""] * (col_index - len(row_cells)))
                text = str(cell.get("text") or "").strip()
                if text:
                    row_cells[col_index - 1] = text
                if not row_ref_id:
                    row_ref_id = str(cell.get("ref_id") or "").strip()
            if not any(str(item or "").strip() for item in row_cells):
                continue
            sample_rows.append(
                {
                    "row_index": row_index if row_index > 0 else len(sample_rows) + 1,
                    "source_row_index": source_row_index if source_row_index > 0 else row_index,
                    "ref_id": row_ref_id or None,
                    "cells": row_cells[:24],
                }
            )
            if len(sample_rows) >= 40:
                break

        if not sample_rows:
            continue

        sheet_index_raw = sheet.get("sheet_index")
        sheet_index = int(sheet_index_raw) if isinstance(sheet_index_raw, (int, float)) else len(samples) + 1
        table_id = f"xlsx_t{max(1, sheet_index)}"
        sample_ref_id = ""
        for row in sample_rows:
            sample_ref_id = str(row.get("ref_id") or "").strip()
            if sample_ref_id:
                break
        samples.append(
            {
                "object_type": "table",
                "table_id": table_id,
                "ref_id": sample_ref_id,
                "page": 1,
                "headers": normalized_headers[:24],
                "rows": sample_rows,
                "row_count": len(sample_rows),
                "col_count": len(normalized_headers[:24]),
            }
        )

    return samples


def ground_answer_with_frontend_context(
    *,
    user_message: str,
    answer: str,
    extra_context: Optional[Dict[str, Any]],
    allow_snapshot_override: bool = True,
) -> str:
    cleaned_answer = cleanup_answer_text(answer)
    if not allow_snapshot_override:
        return cleaned_answer
    snapshot_answer = build_frontend_snapshot_answer(
        user_message=user_message,
        extra_context=extra_context,
    )
    if not snapshot_answer:
        return cleaned_answer
    if should_short_circuit_with_frontend_snapshot(
        user_message=user_message,
        snapshot_answer=snapshot_answer,
        extra_context=extra_context,
    ):
        return snapshot_answer
    if not cleaned_answer or looks_like_placeholder_answer(cleaned_answer):
        return snapshot_answer
    return cleaned_answer


