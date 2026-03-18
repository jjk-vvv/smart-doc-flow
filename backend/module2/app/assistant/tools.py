from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import DocumentExtractionResponse


PERSIST_HINTS = ("入库", "落库", "保存", "存储", "写入数据库", "写库", "数据库")
SQL_HINTS = ("sql", "查询数据库", "更新数据库", "删除数据", "新增数据", "select ", "insert ", "update ", "delete ")
WEB_HINTS = ("联网", "搜索", "查一下", "最新", "最近", "政策", "法规", "新闻", "web", "google", "bing")
FIGURE_HINTS = ("图", "图表", "图片", "chart", "figure", "figure_id", "关键要点", "dataframe", "坐标轴", "趋势")
KNOWLEDGE_HINTS = (
    "ocr",
    "版面分析",
    "布局分析",
    "文档处理",
    "文档解析",
    "信息提取",
    "非结构化",
    "多模态",
    "表格恢复",
    "表格抽取",
    "字段抽取",
    "落库流程",
    "入库流程",
    "pipeline",
    "思路",
    "原理",
    "方法",
    "区别",
    "怎么理解",
    "怎么做",
    "为什么会",
    "为什么总是",
    "最佳实践",
)
SUMMARY_HINTS = (
    "概述",
    "总结",
    "主要讲了什么",
    "整体",
    "总体",
    "大致",
    "大概",
    "讲什么",
    "值得注意",
    "注意点",
    "看点",
    "重点",
    "亮点",
    "异常",
    "风险",
    "问题",
)
TABLE_HINTS = ("表", "表格", "sheet", "xlsx", "行", "列", "站点", "监测值", "那一行", "该行", "这一行")
ROW_FOLLOWUP_HINTS = ("那一行", "该行", "这一行", "同一行", "继续", "继续看", "继续说明", "那行")
EXPLANATORY_QUESTION_HINTS = (
    "为什么",
    "如何",
    "怎么",
    "思路",
    "原理",
    "区别",
    "哪些",
    "哪里",
    "风险",
    "易错",
    "注意",
    "最佳实践",
    "流程",
    "方法",
    "理解",
    "讲讲",
    "说明",
)
EXPLICIT_DATABASE_ACTION_HINTS = (
    "执行",
    "预览",
    "sql",
    "select ",
    "insert ",
    "update ",
    "delete ",
    "写入 ",
    "插入 ",
    "更新 ",
    "删除 ",
    "生成sql",
    "生成 sql",
    "准备入库",
)

LOCK_QUALITY_STABLE = "stable_lock"
LOCK_QUALITY_WEAK = "weak_lock"
LOCK_QUALITY_NONE = "no_lock"

ROW_IDENTIFIER_HEADERS = (
    "站点名称",
    "站点",
    "监测点",
    "站名",
    "站点编码",
    "编码",
    "编号",
    "序号",
)

EXPLICIT_VALUE_FIELD_HINTS = (
    "pm10",
    "pm2.5",
    "pm25",
    "aqi",
    "空气质量指数",
    "污染类型",
    "首要污染物",
    "二氧化硫",
    "二氧化氮",
    "臭氧",
    "一氧化碳",
    "监测值",
    "数值",
    "值",
)

READ_OPERATION_HINTS = ("select ", "查询", "查看", "检索", "读取", "统计", "count", "筛选")
INSERT_OPERATION_HINTS = ("insert ", "新增", "新建", "插入", "写入", "入库", "保存", "落库")
UPDATE_OPERATION_HINTS = ("update ", "更新", "修改", "改成", "改为", "设为", "设置为", "变更", "调整")
DELETE_OPERATION_HINTS = ("delete ", "删除", "删掉", "移除", "清空")
SQL_PREVIEW_ALLOWLIST = {
    "document_extractions",
    "extraction_field_staging",
    "extraction_table_staging",
    "assist_session",
    "assist_message",
}


def _result_root(document: DocumentExtractionResponse) -> Dict[str, Any]:
    root = getattr(document.result, "root", {})
    if not isinstance(root, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in root.items():
        if isinstance(value, dict):
            out[str(key)] = dict(value)
            continue
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="json")
            if isinstance(payload, dict):
                out[str(key)] = payload
                continue
        out[str(key)] = value
    return out


def _trace_hit_dicts(document: DocumentExtractionResponse) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in document.trace_hits or []:
        if isinstance(item, dict):
            out.append(dict(item))
            continue
        if hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
            if isinstance(payload, dict):
                out.append(payload)
    return out


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[\s\-_:/\\|（）()\[\]【】“”\"'‘’，,。；;：:.!?？]+", "", text)


def _contains_text(query: str, candidate: str) -> bool:
    q = _normalize_text(query)
    c = _normalize_text(candidate)
    if not q or not c:
        return False
    return c in q or q in c


def _keyword_overlap_score(query: str, candidate: str) -> int:
    q_norm = _normalize_text(query)
    c_norm = _normalize_text(candidate)
    if not q_norm or not c_norm:
        return 0
    if q_norm == c_norm:
        return 12
    if c_norm in q_norm:
        return min(10, max(3, len(c_norm)))
    if q_norm in c_norm:
        return min(8, max(2, len(q_norm)))
    score = 0
    for token in re.findall(r"[a-z0-9\.\-]+|[\u4e00-\u9fff]{2,}", str(query or "").lower()):
        token_norm = _normalize_text(token)
        if token_norm and token_norm in c_norm:
            score += min(4, max(1, len(token_norm) // 2))
    return score


def _followup_row_query(query: str) -> bool:
    text = str(query or "").strip()
    return any(hint in text for hint in ROW_FOLLOWUP_HINTS)


def _header_score(header: str, query: str) -> int:
    score = _keyword_overlap_score(query, header)
    query_norm = _normalize_text(query)
    header_norm = _normalize_text(header)
    alias_groups = [
        ("pm25", ("pm2.5", "pm25")),
        ("pm10", ("pm10",)),
        ("aqi", ("aqi", "空气质量指数")),
        ("污染类型", ("污染类型",)),
        ("首要污染物", ("首要污染物",)),
        ("站点名称", ("站点名称", "站点", "监测点", "站名")),
        ("日期", ("日期", "时间")),
    ]
    for canonical, aliases in alias_groups:
        alias_hit = any(_normalize_text(alias) in query_norm for alias in aliases)
        if alias_hit and (_normalize_text(canonical) in header_norm or any(_normalize_text(alias) in header_norm for alias in aliases)):
            score += 8
    return score


def _trim_anchor_term(value: str) -> str:
    text = str(value or "").strip().strip("\"'“”‘’")
    if not text:
        return ""
    text = re.sub(r"^(?:为|是|叫|等于|=|:|：)\s*", "", text)
    stop_patterns = (
        r"(?:的)?(?:pm2\.?5|pm10|aqi|空气质量指数|污染类型|首要污染物|"
        r"二氧化硫(?:监测值)?|二氧化氮(?:监测值)?|臭氧(?:监测值)?|一氧化碳(?:监测值)?|"
        r"监测值|数值|值|是多少|是什么|多少|几|情况|数据|记录|信息|结果|内容|详情|"
        r"这一行|那一行|该行|所在行|对应行).*$",
        r"(?:表格|sheet|xlsx|页码|ref_id|row\s*\d+|第\s*\d+\s*行|原始第\s*\d+\s*行).*$",
    )
    for pattern in stop_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    text = re.split(r"[，。；、,.;!?？\s]", text, maxsplit=1)[0].strip()
    text = re.sub(r"(?:这个|该|这条|那条)?(?:站点|记录|对象|数据)$", "", text).strip()
    text = text.rstrip("的").strip()
    return text if len(_normalize_text(text)) >= 2 else ""


def _extract_row_anchor_terms(query: str) -> List[str]:
    text = str(query or "").strip()
    if not text:
        return []
    patterns = (
        r"(?:站点名称|站点|监测点|站名)\s*(?:为|是|叫|叫做|名为|等于|=|:|：)?\s*([^\n\r，。；、,.;!?？]{2,80})",
        r"(?:城市|地区|区域|区县)\s*(?:为|是|叫|叫做|名为|等于|=|:|：)?\s*([^\n\r，。；、,.;!?？]{2,80})",
        r"(?:学校|企业|机构)\s*(?:为|是|叫|叫做|名为|等于|=|:|：)?\s*([^\n\r，。；、,.;!?？]{2,80})",
        r"(?:编号|编码|序号)\s*(?:为|是|等于|=|:|：)?\s*([^\n\r，。；、,.;!?？]{2,80})",
    )
    seen = set()
    terms: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            term = _trim_anchor_term(match.group(1))
            if not term:
                continue
            norm = _normalize_text(term)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            terms.append(term)
    return terms[:4]


def _is_row_identifier_header(header: str) -> bool:
    header_norm = _normalize_text(header)
    if not header_norm:
        return False
    return any(_normalize_text(item) == header_norm for item in ROW_IDENTIFIER_HEADERS)


def _query_requests_explicit_value_field(query: str) -> bool:
    query_norm = _normalize_text(query)
    if not query_norm:
        return False
    return any(_normalize_text(item) in query_norm for item in EXPLICIT_VALUE_FIELD_HINTS)


def _row_anchor_match_score(row: Dict[str, Any], anchor_terms: List[str]) -> int:
    return int(_row_anchor_match_details(row, anchor_terms).get("score", 0) or 0)


def _row_anchor_match_details(row: Dict[str, Any], anchor_terms: List[str]) -> Dict[str, Any]:
    if not anchor_terms:
        return {
            "score": 0,
            "exact_terms": [],
            "fuzzy_terms": [],
            "missing_terms": [],
        }
    score = 0
    exact_terms: List[str] = []
    fuzzy_terms: List[str] = []
    missing_terms: List[str] = []
    for term in anchor_terms:
        best_exact = 0
        best_fuzzy = 0
        for cell in row.get("cells", []):
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            if not text:
                continue
            if _contains_text(term, text):
                best_exact = max(best_exact, min(18, len(_normalize_text(term)) + 6))
                continue
            best_fuzzy = max(best_fuzzy, min(8, _keyword_overlap_score(term, text)))
        if best_exact > 0:
            exact_terms.append(term)
            score += best_exact
        elif best_fuzzy > 0:
            fuzzy_terms.append(term)
            score += best_fuzzy
        else:
            missing_terms.append(term)
    return {
        "score": score,
        "exact_terms": exact_terms,
        "fuzzy_terms": fuzzy_terms,
        "missing_terms": missing_terms,
    }


def _has_explicit_row_locator(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    return bool(re.search(r"(?:第\s*\d+\s*行|row\s*\d+)", text, flags=re.IGNORECASE))


def _extract_explicit_row_number(query: str) -> Optional[int]:
    text = str(query or "").strip()
    if not text:
        return None
    for pattern in (r"表内第\s*(\d+)\s*行", r"原始第\s*(\d+)\s*行", r"第\s*(\d+)\s*行", r"row\s*(\d+)"):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _looks_like_database_explanation_query(text: str) -> bool:
    query = str(text or "").strip().lower()
    if not query:
        return False
    explanation_markers = (
        "为什么",
        "为何",
        "怎么",
        "风险",
        "易错",
        "注意",
        "思路",
        "原理",
        "方法",
        "流程",
        "分阶段",
        "更稳",
        "区别",
        "理解",
        "详细说明",
        "具体风险",
        "不要泛泛而谈",
        "举例",
        "best practice",
    )
    direct_action_markers = (
        "生成sql",
        "生成 sql",
        "给我sql",
        "给我 sql",
        "执行sql",
        "执行 sql",
        "写入数据库",
        "插入数据库",
        "更新数据库",
        "删除数据库",
        "目标表",
        "字段映射",
        "sql语句",
        "sql 语句",
    )
    if not any(marker in query for marker in explanation_markers):
        return False
    return not any(marker in query for marker in direct_action_markers)


def classify_route(
    *,
    user_message: str,
    payload: Dict[str, Any],
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> str:
    text = str(user_message or "").strip().lower()
    if not text:
        return "clarification_needed"
    wants_summary = any(hint in text for hint in SUMMARY_HINTS)
    wants_table = any(hint in text for hint in TABLE_HINTS)
    wants_knowledge = any(hint in text for hint in KNOWLEDGE_HINTS)
    wants_explanation = any(hint in text for hint in EXPLANATORY_QUESTION_HINTS)
    explicit_database_action = any(hint in text for hint in SQL_HINTS) or any(hint in text for hint in EXPLICIT_DATABASE_ACTION_HINTS)
    mentions_database = explicit_database_action or any(hint in text for hint in PERSIST_HINTS)
    database_explanation = (wants_knowledge or wants_explanation) and mentions_database and _looks_like_database_explanation_query(text)

    if database_explanation:
        return "knowledge_explain"
    if mentions_database and wants_knowledge and not explicit_database_action:
        return "knowledge_explain"
    if mentions_database:
        return "database_action"
    if any(hint in text for hint in WEB_HINTS):
        return "web_research"

    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    if any(hint in text for hint in FIGURE_HINTS) or (figures and "图" in text):
        if any(hint in text for hint in SUMMARY_HINTS) or "列出" in text or "有哪些" in text:
            return "figure_overview"
        return "figure_value_read"

    if current_object_lock and str(current_object_lock.get("lock_type", "")).lower() == "table_row" and _followup_row_query(text):
        return "table_lookup"

    if wants_summary:
        return "document_summary"
    if wants_knowledge:
        return "knowledge_explain"
    if wants_table:
        return "table_lookup"
    return "field_lookup"


def match_fields(document: DocumentExtractionResponse, user_message: str, top_k: int = 8) -> List[Dict[str, Any]]:
    instruction = str(user_message or "").strip().lower()
    wants_all = any(token in instruction for token in ("全部", "所有", "全量", "完整"))
    out: List[Tuple[int, Dict[str, Any]]] = []
    for field_name, entity in _result_root(document).items():
        if not isinstance(entity, dict):
            continue
        value = entity.get("value")
        if value is None:
            continue
        label = str(field_name)
        score = 0
        if wants_all:
            score += 2
        score += _keyword_overlap_score(instruction, field_name)
        score += _keyword_overlap_score(instruction, label)
        try:
            confidence = float(entity.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if score <= 0 and not wants_all:
            continue
        page = None
        bbox = entity.get("bbox") if isinstance(entity.get("bbox"), list) else []
        if len(bbox) == 5:
            try:
                page = int(round(float(bbox[0])))
            except Exception:
                page = None
        out.append(
            (
                score,
                {
                    "field_name": str(field_name),
                    "label": label,
                    "value": value,
                    "confidence": confidence,
                    "source_ref_id": entity.get("source_ref_id"),
                    "page": page,
                    "bbox": bbox,
                },
            )
        )
    out.sort(key=lambda item: (item[0], float(item[1].get("confidence", 0.0) or 0.0)), reverse=True)
    if out:
        return [item[1] for item in out[: max(1, int(top_k or 8))]]

    fallback: List[Dict[str, Any]] = []
    for field_name, entity in _result_root(document).items():
        if not isinstance(entity, dict) or entity.get("value") is None:
            continue
        fallback.append(
            {
                "field_name": str(field_name),
                "label": str(field_name),
                "value": entity.get("value"),
                "confidence": float(entity.get("confidence", 0.0) or 0.0),
                "source_ref_id": entity.get("source_ref_id"),
                "page": None,
                "bbox": entity.get("bbox") if isinstance(entity.get("bbox"), list) else [],
            }
        )
    fallback.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
    return fallback[: max(1, min(int(top_k or 8), 4))]


def collect_trace_hits(
    document: DocumentExtractionResponse,
    matched_fields: List[Dict[str, Any]],
    user_message: str,
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    hits = _trace_hit_dicts(document)
    if not hits:
        return []
    wanted_keys = {str(item.get("field_name", "")).lower() for item in matched_fields if item.get("field_name")}
    query = str(user_message or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for hit in hits:
        object_id = str(hit.get("object_id", "")).strip().lower()
        snippet = str(hit.get("snippet", "")).strip().lower()
        if wanted_keys and object_id in wanted_keys:
            out.append(hit)
            continue
        if query and query in snippet:
            out.append(hit)
    if not out:
        out = hits
    out.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
    return out[: max(1, int(top_k or 12))]


def _find_trace_hit(document: DocumentExtractionResponse, object_type: str, object_id: str) -> Optional[Dict[str, Any]]:
    target_type = str(object_type or "").strip().lower()
    target_id = str(object_id or "").strip().lower()
    for hit in _trace_hit_dicts(document):
        if str(hit.get("object_type", "")).strip().lower() != target_type:
            continue
        if str(hit.get("object_id", "")).strip().lower() != target_id:
            continue
        return hit
    return None


def _table_payloads(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    tables = payload.get("tables")
    return list(tables) if isinstance(tables, list) else []


def _figure_payloads(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    figures = payload.get("figures")
    return list(figures) if isinstance(figures, list) else []


_CELL_REF_RE = re.compile(r"^(?P<prefix>.+)_r(?P<row>\d+)_c(?P<col>\d+)$", flags=re.IGNORECASE)


def payload_has_structural_context(payload: Dict[str, Any]) -> bool:
    return bool(_table_payloads(payload) or _figure_payloads(payload))


def merge_structural_payload(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(primary or {})
    fallback_payload = dict(fallback or {})
    if not _table_payloads(out):
        tables = _table_payloads(fallback_payload)
        if tables:
            out["tables"] = tables
    if not _figure_payloads(out):
        figures = _figure_payloads(fallback_payload)
        if figures:
            out["figures"] = figures
    return out


def reconstruct_payload_from_trace_hits(document: DocumentExtractionResponse) -> Dict[str, Any]:
    tables: List[Dict[str, Any]] = []
    figures: List[Dict[str, Any]] = []
    seen_tables: set[str] = set()
    seen_figures: set[str] = set()

    for hit in _trace_hit_dicts(document):
        object_type = str(hit.get("object_type") or "").strip().lower()
        object_id = str(hit.get("object_id") or "").strip()
        if not object_id:
            continue
        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}

        if object_type == "table" and object_id not in seen_tables:
            preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}
            headers = [
                str(item).strip()
                for item in (preview.get("headers") if isinstance(preview.get("headers"), list) else [])
                if str(item).strip()
            ]
            preview_rows_raw = preview.get("rows") if isinstance(preview.get("rows"), list) else []
            preview_rows = [
                [str(cell).strip() for cell in row]
                for row in preview_rows_raw
                if isinstance(row, list) and any(str(cell).strip() for cell in row)
            ]
            if not headers and not preview_rows:
                continue

            ref_id = str(hit.get("ref_id") or "").strip()
            ref_match = _CELL_REF_RE.match(ref_id) if ref_id else None
            ref_prefix = str(ref_match.group("prefix") or "").strip() if ref_match else ""
            ref_row = int(ref_match.group("row")) if ref_match else 0
            ref_col = int(ref_match.group("col")) if ref_match else 0

            start_row = int(locator.get("row_index", 0) or 0) or ref_row or 1
            start_col = int(locator.get("col_index", 0) or 0) or ref_col or 1
            max_cols = max(len(headers), max((len(row) for row in preview_rows), default=0))
            rows: List[Dict[str, Any]] = []
            for row_offset, values in enumerate(preview_rows):
                source_row_index = start_row + row_offset if start_row > 0 else row_offset + 1
                cells: List[Dict[str, Any]] = []
                for col_offset in range(max_cols):
                    text = str(values[col_offset] if col_offset < len(values) else "").strip()
                    header = str(headers[col_offset] if col_offset < len(headers) else "").strip()
                    source_col_index = start_col + col_offset if start_col > 0 else col_offset + 1
                    cell_ref_id = f"{ref_prefix}_r{source_row_index}_c{source_col_index}" if ref_prefix else ""
                    cells.append(
                        {
                            "header": header,
                            "text": text,
                            "ref_id": cell_ref_id,
                            "col_index": source_col_index,
                            "bbox": [],
                        }
                    )
                rows.append(
                    {
                        "row_index": row_offset + 1,
                        "source_row_index": source_row_index,
                        "cells": cells,
                    }
                )

            page = int(hit.get("page", 0) or locator.get("page", 0) or 0) or None
            bbox = hit.get("bbox") if isinstance(hit.get("bbox"), list) else []
            table_payload: Dict[str, Any] = {
                "table_id": object_id,
                "page": page,
                "headers": headers,
                "rows": rows,
                "row_count": len(rows),
                "col_count": max_cols,
                "quality": float(hit.get("confidence", 0.0) or 0.0),
                "bbox_norm": bbox,
                "artifact_path": str(hit.get("artifact_path") or ""),
                "artifact_url": str(hit.get("artifact_url") or ""),
            }
            sheet_name = str(locator.get("sheet_name") or "").strip()
            if sheet_name:
                table_payload["sheet_name"] = sheet_name
            seen_tables.add(object_id)
            tables.append(table_payload)
            continue

        if object_type == "figure" and object_id not in seen_figures:
            dataframe = locator.get("dataframe") if isinstance(locator.get("dataframe"), dict) else {}
            headers = [
                str(item).strip()
                for item in (dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else [])
                if str(item).strip()
            ]
            rows_raw = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
            rows = [
                [str(cell).strip() for cell in row]
                for row in rows_raw
                if isinstance(row, list) and any(str(cell).strip() for cell in row)
            ]
            key_points = [
                str(item).strip()
                for item in (locator.get("key_points") if isinstance(locator.get("key_points"), list) else [])
                if str(item).strip()
            ]
            content_modes = [
                str(item).strip()
                for item in (locator.get("content_modes") if isinstance(locator.get("content_modes"), list) else [])
                if str(item).strip()
            ]
            text_blocks = [
                str(item).strip()
                for item in (locator.get("text_blocks") if isinstance(locator.get("text_blocks"), list) else [])
                if str(item).strip()
            ]
            page = int(hit.get("page", 0) or locator.get("page", 0) or 0) or None
            figures.append(
                {
                    "figure_id": object_id,
                    "page": page,
                    "title": str(locator.get("caption") or object_id),
                    "caption": str(locator.get("caption") or ""),
                    "figure_type": str(locator.get("figure_type") or "other"),
                    "key_points": key_points,
                    "content_modes": content_modes,
                    "text_blocks": text_blocks,
                    "dataframe": {
                        "headers": headers,
                        "rows": rows,
                    },
                    "ref_ids": [str(hit.get("ref_id") or "").strip()] if str(hit.get("ref_id") or "").strip() else [],
                    "artifact_path": str(hit.get("artifact_path") or ""),
                    "artifact_url": str(hit.get("artifact_url") or ""),
                    "bbox": hit.get("bbox") if isinstance(hit.get("bbox"), list) else [],
                    "quality": float(hit.get("confidence", 0.0) or 0.0),
                }
            )
            seen_figures.add(object_id)

    return {
        "tables": tables,
        "figures": figures,
    }


def _split_field_stability(document: DocumentExtractionResponse) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    stable: List[Dict[str, Any]] = []
    unstable: List[Dict[str, Any]] = []
    for field_name, entity in _result_root(document).items():
        if not isinstance(entity, dict):
            continue
        value = entity.get("value")
        text = str(value).strip() if value is not None else ""
        try:
            confidence = float(entity.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        payload = {
            "field_name": str(field_name),
            "value": value,
            "confidence": confidence,
            "source_ref_id": entity.get("source_ref_id"),
        }
        if value is None or not text or text.lower() == "null" or confidence < 0.35:
            unstable.append(payload)
        else:
            stable.append(payload)
    return stable, unstable


def _row_text(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    for cell in row.get("cells", []):
        if not isinstance(cell, dict):
            continue
        text = str(cell.get("text") or "").strip()
        header = str(cell.get("header") or "").strip()
        if header and text:
            parts.append(f"{header}:{text}")
        elif text:
            parts.append(text)
    return " | ".join(parts)


def _row_preview(row: Dict[str, Any], max_cells: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for cell in row.get("cells", [])[:max_cells]:
        if not isinstance(cell, dict):
            continue
        out.append(
            {
                "header": str(cell.get("header") or ""),
                "text": str(cell.get("text") or ""),
                "ref_id": str(cell.get("ref_id") or ""),
                "col_index": int(cell.get("col_index", 0) or 0),
            }
        )
    return out


def _find_row_by_lock(payload: Dict[str, Any], current_object_lock: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    table_id = str(current_object_lock.get("table_id") or "").strip()
    row_index = int(current_object_lock.get("row_index", 0) or 0)
    if not table_id or row_index <= 0:
        return None, None
    for table in _table_payloads(payload):
        if str(table.get("table_id") or "").strip() != table_id:
            continue
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            if int(row.get("row_index", 0) or 0) == row_index:
                return table, row
    return None, None


def _find_row_by_ref_id(payload: Dict[str, Any], ref_id: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ref_text = str(ref_id or "").strip()
    match = _CELL_REF_RE.match(ref_text)
    if not match:
        return None, None
    table_id = str(match.group("prefix") or "").strip()
    source_row_index = int(match.group("row") or 0)
    if not table_id or source_row_index <= 0:
        return None, None
    for table in _table_payloads(payload):
        if str(table.get("table_id") or "").strip() != table_id:
            continue
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            row_source_index = int(row.get("source_row_index", 0) or 0)
            row_index = int(row.get("row_index", 0) or 0)
            if row_source_index == source_row_index or row_index == source_row_index:
                return table, row
    return None, None


def build_current_focus_context(
    payload: Dict[str, Any],
    current_object_lock: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not current_object_lock or not isinstance(current_object_lock, dict):
        return {}

    lock_type = str(current_object_lock.get("lock_type") or "").strip().lower()
    ref_id = str(current_object_lock.get("ref_id") or "").strip() or None
    table_id = str(current_object_lock.get("table_id") or "").strip() or None
    page = current_object_lock.get("page")
    row_index = current_object_lock.get("row_index")
    source_row_index = current_object_lock.get("source_row_index")
    lock_quality = str(current_object_lock.get("lock_quality") or "").strip().lower() or LOCK_QUALITY_STABLE
    metadata = current_object_lock.get("metadata") if isinstance(current_object_lock.get("metadata"), dict) else {}

    if lock_type == "ocr_fact_group":
        fact_preview = metadata.get("fact_preview") if isinstance(metadata.get("fact_preview"), list) else []
        return {
            "lock_type": lock_type,
            "lock_quality": lock_quality,
            "label": str(current_object_lock.get("label") or current_object_lock.get("object_id") or "OCR事实组"),
            "row_label": str(metadata.get("row_label") or "").strip() or None,
            "page": page,
            "table_id": table_id,
            "row_index": row_index,
            "source_row_index": source_row_index,
            "ref_id": ref_id,
            "recognition_tier": str(metadata.get("recognition_tier") or "").strip() or None,
            "snippet": str(metadata.get("snippet") or "").strip(),
            "fact_preview": fact_preview[:4],
            "row_preview": [],
        }

    table = None
    row = None
    if lock_type == "table_row":
        table, row = _find_row_by_lock(payload, current_object_lock)
    elif ref_id:
        table, row = _find_row_by_ref_id(payload, ref_id)

    if table and row:
        resolved_table_id = str(table.get("table_id") or table_id or "")
        resolved_page = int(table.get("page", 0) or page or 0) or None
        resolved_row_index = int(row.get("row_index", 0) or row_index or 0) or None
        resolved_source_row_index = int(row.get("source_row_index", 0) or source_row_index or 0) or None
        header = str(metadata.get("header") or "").strip()
        row_label = str(metadata.get("row_label") or "").strip()
        if not row_label or re.fullmatch(r"\d{5,}", row_label):
            preview_label_cell = _find_preview_cell(_row_preview(row, max_cells=10), "站点名称", "站点", "监测点", "站名", "名称")
            row_label = str((preview_label_cell or {}).get("text") or "").strip()
        return {
            "lock_type": lock_type or "table_row",
            "lock_quality": lock_quality,
            "label": str(current_object_lock.get("label") or current_object_lock.get("object_id") or resolved_table_id or "当前对象"),
            "row_label": row_label or None,
            "page": resolved_page,
            "table_id": resolved_table_id or None,
            "row_index": resolved_row_index,
            "source_row_index": resolved_source_row_index,
            "ref_id": ref_id,
            "header": header or None,
            "snippet": _row_text(row)[:300],
            "row_preview": _row_preview(row, max_cells=10),
        }

    return {
        "lock_type": lock_type or "context",
        "lock_quality": lock_quality,
        "label": str(current_object_lock.get("label") or current_object_lock.get("object_id") or "当前对象"),
        "row_label": str(metadata.get("row_label") or "").strip() or None,
        "page": page,
        "table_id": table_id,
        "row_index": row_index,
        "source_row_index": source_row_index,
        "ref_id": ref_id,
        "header": str(metadata.get("header") or "").strip() or None,
        "snippet": "",
        "row_preview": [],
    }


def _row_group_key(ref_id: Any) -> str:
    ref_text = str(ref_id or "").strip()
    match = _CELL_REF_RE.match(ref_text)
    if not match:
        return ""
    prefix = str(match.group("prefix") or "").strip()
    row_value = str(match.group("row") or "").strip()
    if not prefix or not row_value:
        return ""
    return f"{prefix}_r{row_value}"


def _row_matches_explicit_index(row: Dict[str, Any], explicit_row_index: Optional[int]) -> bool:
    if not explicit_row_index or explicit_row_index <= 0:
        return False
    row_index = int(row.get("row_index", 0) or 0)
    source_row_index = int(row.get("source_row_index", 0) or 0)
    return explicit_row_index in {row_index, source_row_index}


def _build_row_candidate(
    *,
    table: Dict[str, Any],
    row: Dict[str, Any],
    query: str,
    anchor_terms: List[str],
    explicit_row_index: Optional[int],
    preferred_header: str = "",
    match_reason: str = "query_match",
    force_score: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    table_id = str(table.get("table_id") or "").strip()
    if not table_id:
        return None

    score = _keyword_overlap_score(query, table_id)
    anchor_details = _row_anchor_match_details(row, anchor_terms)
    score += int(anchor_details.get("score", 0) or 0)
    explicit_row_hit = _row_matches_explicit_index(row, explicit_row_index)
    if explicit_row_hit:
        score += 18

    best_cell = None
    best_cell_score = -1
    matched_headers: List[str] = []
    seen_headers: set[str] = set()
    direct_identifier_hits: List[Dict[str, Any]] = []
    seen_identifier_values: set[str] = set()
    for cell in row.get("cells", []):
        if not isinstance(cell, dict):
            continue
        header = str(cell.get("header") or "").strip()
        text = str(cell.get("text") or "").strip()
        header_score = _header_score(header, query)
        if header_score > 0 and header not in seen_headers:
            matched_headers.append(header)
            seen_headers.add(header)
        score += min(8, header_score)
        if len(text) >= 2 and _contains_text(query, text):
            score += min(18, len(_normalize_text(text)) + 4)
            text_norm = _normalize_text(text)
            if text_norm and _is_row_identifier_header(header) and text_norm not in seen_identifier_values:
                seen_identifier_values.add(text_norm)
                direct_identifier_hits.append(
                    {
                        "header": header,
                        "text": text,
                        "ref_id": str(cell.get("ref_id") or "").strip() or None,
                    }
                )

        cell_score = header_score
        if preferred_header and header and _normalize_text(header) == _normalize_text(preferred_header):
            cell_score += 2
        if _contains_text(query, text):
            cell_score += 2
        if cell_score > best_cell_score:
            best_cell_score = cell_score
            best_cell = cell

    if force_score is not None:
        score = int(force_score)

    if score <= 0 and force_score is None:
        return None

    row_cells = [cell for cell in row.get("cells", []) if isinstance(cell, dict)]
    row_label = ""
    label_cell = _find_preview_cell(row_cells, "站点名称", "站点", "监测点", "站名", "名称", "项目名称")
    if label_cell:
        row_label = str(label_cell.get("text") or "").strip()
    if not row_label or re.fullmatch(r"\d{5,}", row_label):
        for cell in row_cells:
            text = str(cell.get("text") or "").strip()
            if text and not re.fullmatch(r"\d{5,}", text):
                row_label = text
                break
    if not row_label:
        for cell in row_cells:
            text = str(cell.get("text") or "").strip()
            if text:
                row_label = text
                break

    return {
        "table": table,
        "row": row,
        "score": int(score),
        "match_reason": match_reason,
        "best_cell": best_cell,
        "best_cell_score": best_cell_score,
        "matched_headers": matched_headers[:4],
        "exact_anchor_terms": list(anchor_details.get("exact_terms") or [])[:4],
        "fuzzy_anchor_terms": list(anchor_details.get("fuzzy_terms") or [])[:4],
        "missing_anchor_terms": list(anchor_details.get("missing_terms") or [])[:4],
        "direct_identifier_hits": direct_identifier_hits[:3],
        "explicit_row_hit": explicit_row_hit,
        "row_label": row_label,
    }


def _summarize_row_candidate(candidate: Dict[str, Any], rank: int) -> Dict[str, Any]:
    table = candidate.get("table") if isinstance(candidate.get("table"), dict) else {}
    row = candidate.get("row") if isinstance(candidate.get("row"), dict) else {}
    best_cell = candidate.get("best_cell") if isinstance(candidate.get("best_cell"), dict) else {}
    return {
        "rank": rank,
        "table_id": str(table.get("table_id") or ""),
        "page": int(table.get("page", 0) or 0) or None,
        "row_index": int(row.get("row_index", 0) or 0) or None,
        "source_row_index": int(row.get("source_row_index", 0) or 0) or None,
        "match_reason": str(candidate.get("match_reason") or ""),
        "score": int(candidate.get("score", 0) or 0),
        "row_label": str(candidate.get("row_label") or ""),
        "matched_headers": list(candidate.get("matched_headers") or [])[:4],
        "matched_anchor_terms": list(candidate.get("exact_anchor_terms") or [])[:4],
        "near_anchor_terms": list(candidate.get("fuzzy_anchor_terms") or [])[:4],
        "missing_anchor_terms": list(candidate.get("missing_anchor_terms") or [])[:4],
        "direct_identifier_hits": list(candidate.get("direct_identifier_hits") or [])[:3],
        "best_cell_header": str(best_cell.get("header") or "").strip() or None,
        "best_cell_value": str(best_cell.get("text") or "").strip() or None,
        "best_ref_id": str(best_cell.get("ref_id") or "").strip() or None,
        "row_preview": _row_preview(row, max_cells=8),
    }


def _candidate_to_table_lookup_result(
    *,
    document: DocumentExtractionResponse,
    candidate: Dict[str, Any],
    used_context_lock: bool,
    lock_quality: str,
) -> Dict[str, Any]:
    table = candidate.get("table") if isinstance(candidate.get("table"), dict) else {}
    row = candidate.get("row") if isinstance(candidate.get("row"), dict) else {}
    best_cell = candidate.get("best_cell") if isinstance(candidate.get("best_cell"), dict) else {}
    table_id = str(table.get("table_id") or "")
    trace_hit = _find_trace_hit(document, "table", table_id)
    page = int(table.get("page", 0) or 0) or int((trace_hit or {}).get("page", 0) or 0) or None
    row_index = int(row.get("row_index", 0) or 0) or None
    source_row_index = int(row.get("source_row_index", 0) or 0) or row_index
    ref_id = str(best_cell.get("ref_id") or "").strip() or None
    value = str(best_cell.get("text") or "").strip()
    header = str(best_cell.get("header") or "").strip()
    row_label = str(candidate.get("row_label") or "").strip()
    citation = {
        "citation_type": "table",
        "title": row_label or f"表格 {table_id}",
        "page": page,
        "ref_id": ref_id,
        "object_id": table_id,
        "snippet": _row_text(row)[:300],
        "payload": {
            "table_id": table_id,
            "page": page,
            "row_index": row_index,
            "source_row_index": source_row_index,
            "ref_id": ref_id,
            "header": header,
            "value": value,
            "row_label": row_label,
            "row_preview": _row_preview(row),
            "artifact_url": str((trace_hit or {}).get("artifact_url") or ""),
            "artifact_path": str((trace_hit or {}).get("artifact_path") or ""),
        },
    }
    current_lock = {
        "lock_type": "table_row",
        "lock_quality": lock_quality,
        "object_id": table_id,
        "label": f"{row_label}这条记录" if row_label else f"{table_id} 当前记录",
        "row_label": row_label or None,
        "page": page,
        "ref_id": ref_id,
        "table_id": table_id,
        "row_index": row_index,
        "source_row_index": source_row_index,
        "metadata": {
            "header": header,
            "row_label": row_label,
        },
    }
    return {
        "route": "table_lookup",
        "lock_quality": lock_quality,
        "value": value,
        "header": header,
        "table_id": table_id,
        "page": page,
        "row_index": row_index,
        "source_row_index": source_row_index,
        "ref_id": ref_id,
        "snippet": _row_text(row),
        "citation": citation,
        "current_object_lock": current_lock,
        "used_context_lock": used_context_lock,
    }


def assess_table_lookup(
    *,
    document: DocumentExtractionResponse,
    payload: Dict[str, Any],
    user_message: str,
    current_object_lock: Optional[Dict[str, Any]] = None,
    max_candidates: int = 3,
) -> Dict[str, Any]:
    query = str(user_message or "").strip()
    anchor_terms = _extract_row_anchor_terms(query)
    explicit_row_index = _extract_explicit_row_number(query)
    has_row_lock = bool(
        current_object_lock
        and str(current_object_lock.get("lock_type", "")).lower() == "table_row"
    )
    followup_without_lock = _followup_row_query(query) and not has_row_lock and not anchor_terms and not explicit_row_index
    preferred_header = ""
    if current_object_lock and _followup_row_query(query) and not _query_requests_explicit_value_field(query):
        preferred_header = str(current_object_lock.get("metadata", {}).get("header") or "")
    used_context_lock = False

    if followup_without_lock:
        return {
            "resolved": False,
            "lock_quality": LOCK_QUALITY_NONE,
            "clarification_reason": "followup_without_locked_row",
            "query": query,
            "anchor_terms": anchor_terms,
            "missing_anchor_terms": anchor_terms,
            "candidate_rows": [],
        }

    locked_table = None
    locked_row = None
    if current_object_lock and str(current_object_lock.get("lock_type") or "").strip().lower() == "table_row" and _followup_row_query(query):
        locked_table, locked_row = _find_row_by_lock(payload, current_object_lock)
        if locked_table is not None and locked_row is not None:
            used_context_lock = True

    candidates: List[Dict[str, Any]] = []
    if locked_table is not None and locked_row is not None:
        candidate = _build_row_candidate(
            table=locked_table,
            row=locked_row,
            query=query,
            anchor_terms=anchor_terms,
            explicit_row_index=explicit_row_index,
            preferred_header=preferred_header,
            match_reason="current_table_row_lock",
            force_score=999,
        )
        if candidate:
            candidates.append(candidate)
    else:
        for table in _table_payloads(payload):
            if not isinstance(table, dict):
                continue
            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue
                candidate = _build_row_candidate(
                    table=table,
                    row=row,
                    query=query,
                    anchor_terms=anchor_terms,
                    explicit_row_index=explicit_row_index,
                    preferred_header=preferred_header,
                )
                if candidate:
                    candidates.append(candidate)

    if not candidates:
        return {
            "resolved": False,
            "lock_quality": LOCK_QUALITY_NONE,
            "clarification_reason": "no_matching_row",
            "query": query,
            "anchor_terms": anchor_terms,
            "missing_anchor_terms": anchor_terms,
            "candidate_rows": [],
        }

    candidates.sort(
        key=lambda item: (
            int(item.get("score", 0) or 0),
            len(item.get("exact_anchor_terms") or []),
            len(item.get("direct_identifier_hits") or []),
            1 if item.get("explicit_row_hit") else 0,
            str(((item.get("table") or {}) if isinstance(item.get("table"), dict) else {}).get("table_id") or ""),
        ),
        reverse=True,
    )
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    best_exact_count = len(best.get("exact_anchor_terms") or [])
    all_anchor_matched = bool(anchor_terms) and best_exact_count == len(anchor_terms)
    best_identifier_hit_count = len(best.get("direct_identifier_hits") or [])
    second_identifier_hit_count = len((second or {}).get("direct_identifier_hits") or [])
    score_gap = int(best.get("score", 0) or 0) - int((second or {}).get("score", 0) or 0)
    ambiguous = bool(second) and score_gap < 6
    unique_direct_identifier_lock = best_identifier_hit_count > 0 and second_identifier_hit_count == 0

    lock_quality = LOCK_QUALITY_WEAK
    clarification_reason = "weak_row_grounding"
    if str(best.get("match_reason") or "") == "current_table_row_lock":
        lock_quality = LOCK_QUALITY_STABLE
        clarification_reason = ""
    elif explicit_row_index and bool(best.get("explicit_row_hit")) and int(best.get("best_cell_score", 0) or 0) > 0:
        if not anchor_terms or all_anchor_matched:
            lock_quality = LOCK_QUALITY_STABLE
            clarification_reason = ""
    elif anchor_terms and all_anchor_matched and int(best.get("best_cell_score", 0) or 0) > 0 and not ambiguous:
        lock_quality = LOCK_QUALITY_STABLE
        clarification_reason = ""
    elif unique_direct_identifier_lock and int(best.get("best_cell_score", 0) or 0) > 0:
        lock_quality = LOCK_QUALITY_STABLE
        clarification_reason = ""
    elif anchor_terms:
        clarification_reason = "anchor_terms_unresolved"
    elif ambiguous:
        clarification_reason = "candidate_ambiguity"

    result = {
        "resolved": lock_quality == LOCK_QUALITY_STABLE and isinstance(best.get("best_cell"), dict),
        "lock_quality": lock_quality,
        "clarification_reason": clarification_reason,
        "query": query,
        "anchor_terms": anchor_terms,
        "missing_anchor_terms": list(best.get("missing_anchor_terms") or anchor_terms),
        "candidate_rows": [_summarize_row_candidate(item, rank + 1) for rank, item in enumerate(candidates[: max(1, max_candidates)])],
        "best_candidate": _summarize_row_candidate(best, 1),
        "used_context_lock": used_context_lock,
        "ambiguous": ambiguous,
    }
    if result["resolved"]:
        result.update(
            _candidate_to_table_lookup_result(
                document=document,
                candidate=best,
                used_context_lock=used_context_lock,
                lock_quality=lock_quality,
            )
        )
    return result


def _resolve_preview_row(
    payload: Dict[str, Any],
    matched_fields: List[Dict[str, Any]],
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str, str]:
    if current_object_lock:
        lock_type = str(current_object_lock.get("lock_type") or "").strip().lower()
        lock_quality = str(current_object_lock.get("lock_quality") or "").strip().lower() or LOCK_QUALITY_STABLE
        if lock_type == "table_row":
            table, row = _find_row_by_lock(payload, current_object_lock)
            if table and row:
                return table, row, "current_table_row_lock", lock_quality
        lock_ref_id = current_object_lock.get("ref_id")
        if lock_ref_id:
            table, row = _find_row_by_ref_id(payload, lock_ref_id)
            if table and row:
                return table, row, "current_lock_ref", lock_quality

    by_group: Dict[str, Dict[str, Any]] = {}
    for item in matched_fields:
        if not isinstance(item, dict):
            continue
        ref_id = item.get("source_ref_id")
        group_key = _row_group_key(ref_id)
        if not group_key:
            continue
        try:
            confidence = float(item.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        state = by_group.setdefault(group_key, {"score": 0.0, "ref_id": ref_id})
        state["score"] = float(state.get("score", 0.0) or 0.0) + max(0.2, confidence)

    if not by_group:
        return None, None, "", LOCK_QUALITY_NONE

    best_group = max(
        by_group.items(),
        key=lambda pair: (
            float(pair[1].get("score", 0.0) or 0.0),
            str(pair[0]),
        ),
    )
    table, row = _find_row_by_ref_id(payload, best_group[1].get("ref_id"))
    if table and row:
        return table, row, "matched_field_row_cluster", LOCK_QUALITY_WEAK
    return None, None, "", LOCK_QUALITY_NONE


def _build_row_field_bindings(
    row: Dict[str, Any],
    matched_fields: List[Dict[str, Any]],
    page: Optional[int],
) -> List[Dict[str, Any]]:
    row_cells = [cell for cell in row.get("cells", []) if isinstance(cell, dict)]
    row_ref_ids = {str(cell.get("ref_id") or "").strip() for cell in row_cells if str(cell.get("ref_id") or "").strip()}
    row_cells_by_ref = {
        str(cell.get("ref_id") or "").strip(): cell
        for cell in row_cells
        if str(cell.get("ref_id") or "").strip()
    }
    row_headers = {
        _normalize_text(cell.get("header")): cell
        for cell in row_cells
        if _normalize_text(cell.get("header"))
    }
    bindings: List[Dict[str, Any]] = []
    seen_refs: set[str] = set()

    for item in matched_fields:
        if not isinstance(item, dict):
            continue
        ref_id = str(item.get("source_ref_id") or "").strip()
        header_key = _normalize_text(item.get("label") or item.get("field_name") or "")
        source_cell: Optional[Dict[str, Any]] = None
        include = False
        if ref_id and ref_id in row_ref_ids:
            include = True
            source_cell = row_cells_by_ref.get(ref_id)
        elif header_key and header_key in row_headers:
            include = True
            source_cell = row_headers[header_key]
            ref_id = str(source_cell.get("ref_id") or ref_id).strip()
        if not include:
            continue
        if ref_id and ref_id in seen_refs:
            continue
        seen_refs.add(ref_id)
        value = source_cell.get("text") if isinstance(source_cell, dict) else item.get("value")
        label = str((source_cell or {}).get("header") or item.get("label") or item.get("field_name") or "字段")
        bindings.append(
            {
                "field_name": str(item.get("field_name") or ""),
                "label": label,
                "value": value,
                "source_ref_id": ref_id or None,
                "page": item.get("page") or page,
                "confidence": float(item.get("confidence", 0.0) or 0.0),
            }
        )

    if bindings:
        bindings.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
        return bindings[:8]

    fallback_bindings: List[Dict[str, Any]] = []
    for cell in row_cells[:6]:
        fallback_bindings.append(
            {
                "field_name": str(cell.get("header") or ""),
                "label": str(cell.get("header") or "字段"),
                "value": cell.get("text"),
                "source_ref_id": str(cell.get("ref_id") or "").strip() or None,
                "page": page,
                "confidence": None,
            }
        )
    return fallback_bindings


def locate_table_answer(
    *,
    document: DocumentExtractionResponse,
    payload: Dict[str, Any],
    user_message: str,
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    assessment = assess_table_lookup(
        document=document,
        payload=payload,
        user_message=user_message,
        current_object_lock=current_object_lock,
    )
    if not bool(assessment.get("resolved")):
        return None
    return assessment


def select_figures(
    *,
    document: DocumentExtractionResponse,
    payload: Dict[str, Any],
    user_message: str,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    query = str(user_message or "").strip()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for figure in _figure_payloads(payload):
        figure_id = str(figure.get("figure_id") or "").strip()
        caption = str(figure.get("caption") or "").strip()
        title = str(figure.get("title") or "").strip()
        score = _keyword_overlap_score(query, figure_id)
        score += _keyword_overlap_score(query, caption)
        score += _keyword_overlap_score(query, title)
        if score <= 0:
            score = 1
        scored.append((score, figure))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[: max(1, int(top_k or 6))]]


def select_tables(payload: Dict[str, Any], user_message: str, top_k: int = 2) -> List[Dict[str, Any]]:
    query = str(user_message or "").strip()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for table in _table_payloads(payload):
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or "").strip()
        headers = [str(item).strip() for item in (table.get("headers") if isinstance(table.get("headers"), list) else []) if str(item).strip()]
        score = _keyword_overlap_score(query, table_id)
        score += sum(min(6, _header_score(header, query)) for header in headers[:8])
        if score <= 0:
            score = 1
        scored.append((score, table))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[: max(1, int(top_k or 2))]]


def build_table_overview_context(tables: List[Dict[str, Any]], max_rows: int = 3, max_cells: int = 5) -> List[Dict[str, Any]]:
    overview: List[Dict[str, Any]] = []
    for table in tables[:3]:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        preview_rows: List[Dict[str, Any]] = []
        for row in rows[:max_rows]:
            if not isinstance(row, dict):
                continue
            cells = []
            for cell in row.get("cells", [])[:max_cells]:
                if not isinstance(cell, dict):
                    continue
                text = str(cell.get("text") or "").strip()
                if not text:
                    continue
                cells.append(
                    {
                        "header": str(cell.get("header") or ""),
                        "text": text,
                        "ref_id": str(cell.get("ref_id") or "") or None,
                        "col_index": int(cell.get("col_index", 0) or 0) or None,
                    }
                )
            if not cells:
                continue
            preview_rows.append(
                {
                    "row_index": int(row.get("row_index", 0) or 0) or None,
                    "source_row_index": int(row.get("source_row_index", 0) or 0) or None,
                    "cells": cells,
                }
            )
        overview.append(
            {
                "table_id": str(table.get("table_id") or ""),
                "page": int(table.get("page", 0) or 0) or None,
                "headers": [str(item).strip() for item in (table.get("headers") if isinstance(table.get("headers"), list) else []) if str(item).strip()][:8],
                "row_count": int(table.get("row_count", 0) or len(rows) or 0),
                "col_count": int(table.get("col_count", 0) or 0),
                "preview_rows": preview_rows,
            }
        )
    return overview


def build_field_facts_from_table_overviews(table_overviews: List[Dict[str, Any]], max_items: int = 6) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    seen_refs: set[str] = set()
    for table in table_overviews[:3]:
        if not isinstance(table, dict):
            continue
        page = table.get("page")
        preview_rows = table.get("preview_rows") if isinstance(table.get("preview_rows"), list) else []
        for row in preview_rows[:3]:
            if not isinstance(row, dict):
                continue
            cells = row.get("cells") if isinstance(row.get("cells"), list) else []
            for cell in cells[:6]:
                if not isinstance(cell, dict):
                    continue
                value = str(cell.get("text") or "").strip()
                if not value:
                    continue
                ref_id = str(cell.get("ref_id") or "").strip()
                if ref_id and ref_id in seen_refs:
                    continue
                if ref_id:
                    seen_refs.add(ref_id)
                header = str(cell.get("header") or "").strip() or f"col_{cell.get('col_index') or '?'}"
                facts.append(
                    {
                        "field_name": header,
                        "label": header,
                        "value": value,
                        "source_ref_id": ref_id or None,
                        "page": page,
                        "confidence": None,
                    }
                )
                if len(facts) >= max(1, int(max_items or 6)):
                    return facts
    return facts


def build_ocr_fact_group_lock(
    *,
    fallback_tables: List[Dict[str, Any]],
    fallback_fields: List[Dict[str, Any]],
    recognition_tier: str,
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not fallback_tables and not fallback_fields:
        return None

    existing_id = ""
    if current_object_lock and str(current_object_lock.get("lock_type") or "").strip().lower() == "ocr_fact_group":
        existing_id = str(current_object_lock.get("object_id") or "").strip()

    first_table = fallback_tables[0] if fallback_tables and isinstance(fallback_tables[0], dict) else {}
    first_field = fallback_fields[0] if fallback_fields and isinstance(fallback_fields[0], dict) else {}
    first_table_rows = first_table.get("preview_rows") if isinstance(first_table.get("preview_rows"), list) else []
    first_row = first_table_rows[0] if first_table_rows and isinstance(first_table_rows[0], dict) else {}
    first_cells = first_row.get("cells") if isinstance(first_row.get("cells"), list) else []
    first_cell = first_cells[0] if first_cells and isinstance(first_cells[0], dict) else {}

    page = (
        first_table.get("page")
        or first_field.get("page")
        or None
    )
    lock_ref_id = str((current_object_lock or {}).get("ref_id") or "").strip()
    ref_id = str(
        first_field.get("source_ref_id")
        or first_cell.get("ref_id")
        or lock_ref_id
    ).strip() or None
    object_id = existing_id or f"ocr_fact_group:{str(first_table.get('table_id') or ref_id or first_field.get('field_name') or 'default')}"

    fact_preview: List[Dict[str, Any]] = []
    for table in fallback_tables[:2]:
        if not isinstance(table, dict):
            continue
        headers = table.get("headers") if isinstance(table.get("headers"), list) else []
        fact_preview.append(
            {
                "kind": "table",
                "table_id": str(table.get("table_id") or ""),
                "page": table.get("page"),
                "headers": [str(item).strip() for item in headers[:4] if str(item).strip()],
                "row_preview": list(table.get("preview_rows") or [])[:2],
            }
        )
    for field in fallback_fields[:4]:
        if not isinstance(field, dict):
            continue
        fact_preview.append(
            {
                "kind": "field",
                "label": str(field.get("label") or field.get("field_name") or "字段"),
                "value": field.get("value"),
                "page": field.get("page"),
                "ref_id": str(field.get("source_ref_id") or "").strip() or None,
            }
        )

    snippet = ""
    if fact_preview:
        first_preview = fact_preview[0]
        if str(first_preview.get("kind") or "") == "field":
            snippet = f"{str(first_preview.get('label') or '字段')}: {str(first_preview.get('value') or '')}"
        else:
            row_preview = first_preview.get("row_preview") if isinstance(first_preview.get("row_preview"), list) else []
            if row_preview and isinstance(row_preview[0], dict):
                cells = row_preview[0].get("cells") if isinstance(row_preview[0].get("cells"), list) else []
                snippet = " | ".join(
                    f"{str(cell.get('header') or 'col')}={str(cell.get('text') or '')}"
                    for cell in cells[:4]
                    if isinstance(cell, dict) and str(cell.get("text") or "").strip()
                )

    return {
        "lock_type": "ocr_fact_group",
        "lock_quality": LOCK_QUALITY_STABLE,
        "object_id": object_id,
        "label": "当前 OCR 事实组",
        "page": page,
        "ref_id": ref_id,
        "metadata": {
            "recognition_tier": recognition_tier,
            "snippet": snippet[:300],
            "fact_preview": fact_preview[:6],
            "fact_tables": fallback_tables[:2],
            "fact_fields": fallback_fields[:4],
        },
    }


def build_figure_citations(document: DocumentExtractionResponse, figures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    for figure in figures:
        figure_id = str(figure.get("figure_id") or "").strip()
        if not figure_id:
            continue
        hit = _find_trace_hit(document, "figure", figure_id)
        page = int(figure.get("page", 0) or 0) or int((hit or {}).get("page", 0) or 0) or None
        key_points_raw = figure.get("key_points")
        if not isinstance(key_points_raw, list):
            key_points_raw = figure.get("insights") if isinstance(figure.get("insights"), list) else []
        key_points = [str(item).strip() for item in key_points_raw if str(item).strip()][:4]
        dataframe = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
        df_headers = dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else []
        df_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        citations.append(
            {
                "citation_type": "figure",
                "title": str(figure.get("caption") or figure.get("title") or figure_id),
                "page": page,
                "ref_id": str((hit or {}).get("ref_id") or "") or None,
                "object_id": figure_id,
                "snippet": str((hit or {}).get("snippet") or figure.get("caption") or "")[:300],
                "payload": {
                    "figure_id": figure_id,
                    "page": page,
                    "caption": str(figure.get("caption") or ""),
                    "figure_type": str(figure.get("figure_type") or figure.get("type") or "other"),
                    "key_points": key_points,
                    "dataframe_headers": [str(item).strip() for item in df_headers[:8] if str(item).strip()],
                    "dataframe_rows": [
                        [str(cell).strip() for cell in row[:8]]
                        for row in df_rows[:4]
                        if isinstance(row, list) and any(str(cell).strip() for cell in row)
                    ],
                    "content_modes": [
                        str(item).strip()
                        for item in (figure.get("content_modes") if isinstance(figure.get("content_modes"), list) else [])
                        if str(item).strip()
                    ][:4],
                    "artifact_url": str((hit or {}).get("artifact_url") or figure.get("artifact_url") or ""),
                    "artifact_path": str((hit or {}).get("artifact_path") or figure.get("artifact_path") or ""),
                },
            }
        )
    return citations


def build_table_overview_citations(document: DocumentExtractionResponse, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    for table in tables[:3]:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or "").strip()
        if not table_id:
            continue
        hit = _find_trace_hit(document, "table", table_id)
        preview_rows = table.get("preview_rows") if isinstance(table.get("preview_rows"), list) else []
        first_row = preview_rows[0] if preview_rows and isinstance(preview_rows[0], dict) else {}
        first_cells = first_row.get("cells") if isinstance(first_row.get("cells"), list) else []
        row_text = " | ".join(
            f"{str(cell.get('header') or 'col')}:{str(cell.get('text') or '')}"
            for cell in first_cells[:4]
            if isinstance(cell, dict) and str(cell.get("text") or "").strip()
        )
        first_ref_id = ""
        for cell in first_cells:
            if not isinstance(cell, dict):
                continue
            ref_id = str(cell.get("ref_id") or "").strip()
            if ref_id:
                first_ref_id = ref_id
                break
        citations.append(
            {
                "citation_type": "table",
                "title": f"表格 {table_id}",
                "page": table.get("page"),
                "ref_id": first_ref_id or str((hit or {}).get("ref_id") or "") or None,
                "object_id": table_id,
                "snippet": str((hit or {}).get("snippet") or row_text or table_id)[:300],
                "payload": {
                    "table_id": table_id,
                    "page": table.get("page"),
                    "row_count": table.get("row_count"),
                    "col_count": table.get("col_count"),
                    "headers": table.get("headers") if isinstance(table.get("headers"), list) else [],
                    "preview_rows": preview_rows[:3],
                    "artifact_url": str((hit or {}).get("artifact_url") or ""),
                    "artifact_path": str((hit or {}).get("artifact_path") or ""),
                },
            }
        )
    return citations


def build_document_overview(
    *,
    document: DocumentExtractionResponse,
    payload: Dict[str, Any],
    summary_text: str,
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fields = _result_root(document)
    stable_fields, unstable_fields = _split_field_stability(document)
    tables = _table_payloads(payload)
    figures = _figure_payloads(payload)
    current_focus = build_current_focus_context(payload, current_object_lock)
    top_field_names = [str(item.get("field_name") or "") for item in stable_fields[:8] if str(item.get("field_name") or "").strip()]
    top_tables = [str(table.get("table_id") or "") for table in tables[:6] if str(table.get("table_id") or "").strip()]
    top_figures = [
        {
            "figure_id": str(figure.get("figure_id") or ""),
            "page": int(figure.get("page", 0) or 0) or None,
            "caption": str(figure.get("caption") or figure.get("title") or ""),
        }
        for figure in figures[:6]
    ]
    return {
        "summary_text": str(summary_text or "").strip(),
        "evidence_scope": "当前概览主要基于已抽取的结构化字段、表格和图表对象，不代表已经完成整表统计或趋势分析。",
        "current_focus": current_focus,
        "field_count": len(fields),
        "stable_field_count": len(stable_fields),
        "unstable_field_count": len(unstable_fields),
        "table_count": len(tables),
        "figure_count": len(figures),
        "top_fields": top_field_names,
        "stable_fields": stable_fields[:8],
        "unstable_fields": unstable_fields[:8],
        "top_tables": top_tables,
        "top_figures": top_figures,
        "soft_warnings": list(document.soft_warnings or [])[:6],
        "errors": list(document.errors or [])[:4],
    }


def _binding_label(item: Dict[str, Any]) -> str:
    return str(item.get("label") or item.get("field_name") or "").strip()


def _binding_value(item: Dict[str, Any]) -> Any:
    return item.get("value")


def _quote_sql_identifier(identifier: str) -> str:
    raw = str(identifier or "").strip().strip("`")
    if not raw:
        return '""'
    parts = [part.strip().strip('"') for part in raw.split(".") if part.strip()]
    if not parts:
        return '""'
    return ".".join(f'"{part.replace(chr(34), chr(34) * 2)}"' for part in parts)


def _quote_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def _infer_database_operation(query: str, action_type: str) -> str:
    text = str(query or "").strip().lower()
    if any(hint in text for hint in DELETE_OPERATION_HINTS):
        return "delete"
    if any(hint in text for hint in UPDATE_OPERATION_HINTS):
        return "update"
    if any(hint in text for hint in INSERT_OPERATION_HINTS):
        return "insert"
    if any(hint in text for hint in READ_OPERATION_HINTS):
        return "select"
    return "select" if str(action_type or "").strip().lower() == "sql_preview" else "insert"


def _normalize_target_table_name(value: str) -> str:
    text = str(value or "").strip().strip("`").strip()
    if not text:
        return ""
    text = text.rstrip("，。；、,.;!?？").strip()
    text = re.sub(r"(?:表|table)$", "", text, flags=re.IGNORECASE).strip()
    text = text.strip('"').strip()
    if not text:
        return ""
    if not re.fullmatch(r"[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63}", text):
        return ""
    stopwords = {"数据库", "sql", "where", "select", "insert", "update", "delete"}
    return "" if text.lower() in stopwords else text


def _extract_target_table_name(query: str) -> str:
    text = str(query or "").strip()
    if not text:
        return ""
    patterns = (
        r"\bfrom\s+([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63})",
        r"\binto\s+([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63})",
        r"\bupdate\s+([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63})",
        r"(?:写入|保存到|入库到|插入到|新增到|同步到|更新|修改|删除|查询|查看|读取)\s+([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63})\s*(?:表)?",
        r"(?:在|对)\s*([A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\.]{0,63})\s*表",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = _normalize_target_table_name(match.group(1))
        if candidate:
            return candidate
    return ""


def _table_validation_status(target_table: str) -> str:
    normalized = str(target_table or "").strip().lower().split(".")[-1]
    if not normalized:
        return "missing"
    return "whitelisted" if normalized in SQL_PREVIEW_ALLOWLIST else "unregistered"


def _build_predicate_bindings(field_bindings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    predicates = [
        dict(item)
        for item in field_bindings
        if isinstance(item, dict) and _is_row_identifier_header(_binding_label(item)) and _binding_value(item) not in {None, ""}
    ]
    if predicates:
        return predicates[:3]
    return [
        dict(item)
        for item in field_bindings[:3]
        if isinstance(item, dict) and _binding_value(item) not in {None, ""}
    ]


def _extract_assignment_bindings(query: str, field_bindings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text = str(query or "").strip()
    if not text:
        return []
    assignments: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in field_bindings:
        if not isinstance(item, dict):
            continue
        label = _binding_label(item)
        if not label:
            continue
        patterns = (
            rf"(?:把|将)?{re.escape(label)}(?:字段)?(?:改成|改为|更新为|设为|设置为|变更为|调整为)\s*([^\n\r，。；、,.;!?？]{{1,80}})",
            rf"{re.escape(label)}\s*=\s*([^\n\r，。；、,.;!?？]{{1,80}})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = str(match.group(1) or "").strip().strip("\"'“”‘’")
            if not value:
                continue
            key = _normalize_text(label)
            if key in seen:
                continue
            seen.add(key)
            assignments.append(
                {
                    "field_name": str(item.get("field_name") or label),
                    "label": label,
                    "value": value,
                }
            )
            break
    return assignments


def _describe_affected_scope(operation_type: str, preview_payload: Dict[str, Any]) -> str:
    focus_scope = str(preview_payload.get("focus_scope") or "").strip().lower()
    if focus_scope == "table_row":
        record_scope = "当前只基于一条已锁定的表格记录"
    elif focus_scope == "ocr_fact_group":
        record_scope = "当前只基于已锁定的 OCR 事实组，不会自动扩写到整份文档"
    else:
        record_scope = "当前只基于已识别的局部绑定结果，不会默认扩大到整库或整表"
    if operation_type == "select":
        return f"{record_scope} 生成只读查询预览。"
    if operation_type == "insert":
        return f"{record_scope} 生成单条写入预览。"
    if operation_type == "update":
        return f"{record_scope} 生成带 WHERE 条件的更新预览。"
    if operation_type == "delete":
        return f"{record_scope} 生成删除预览，执行前必须二次确认。"
    return record_scope


def _build_confirmation_checklist(
    operation_type: str,
    *,
    target_table: str,
    table_status: str,
    sql_ready: bool,
    missing_requirements: List[str],
) -> List[str]:
    checks: List[str] = []
    if target_table:
        status_label = "已在白名单内" if table_status == "whitelisted" else "还未进入白名单"
        checks.append(f"确认目标表 {target_table} 是否正确，当前状态是 {status_label}。")
    else:
        checks.append("确认目标表名；没有表名时我不会把预览推进为可执行 SQL。")
    if operation_type == "select":
        checks.append("确认 WHERE 条件只用于读取你要看的那条记录，不会误扩大查询范围。")
    elif operation_type == "insert":
        checks.append("确认字段映射和字段类型正确，尤其是主键、时间字段和数值字段。")
        checks.append("确认这次预览只会写入当前这条记录，而不是批量写入整表。")
    elif operation_type == "update":
        checks.append("确认更新字段和值无误，并保留足够严格的 WHERE 条件。")
        checks.append("确认修改范围仍然只对应当前锁定对象。")
    elif operation_type == "delete":
        checks.append("确认删除范围确实只对应当前锁定对象。")
        checks.append("删除属于高风险动作，正式执行前还需要一次二次确认。")
    if missing_requirements:
        checks.append("当前仍缺少这些条件：" + "；".join(missing_requirements[:4]))
    elif sql_ready:
        checks.append("确认后我仍应先走审计记录，再进入真正执行阶段。")
    return checks[:5]


def _build_database_action_details(
    *,
    user_message: str,
    action_type: str,
    preview_payload: Dict[str, Any],
) -> Dict[str, Any]:
    operation_type = _infer_database_operation(user_message, action_type)
    target_table = _extract_target_table_name(user_message)
    table_status = _table_validation_status(target_table)
    preview_status = str(preview_payload.get("preview_status") or "ready").strip().lower()
    lock_quality = str(preview_payload.get("lock_quality") or LOCK_QUALITY_NONE).strip().lower()
    field_bindings = preview_payload.get("field_bindings") if isinstance(preview_payload.get("field_bindings"), list) else []
    safe_field_bindings = [dict(item) for item in field_bindings if isinstance(item, dict)]
    predicate_bindings = _build_predicate_bindings(safe_field_bindings)
    assignment_bindings = _extract_assignment_bindings(user_message, safe_field_bindings) if operation_type == "update" else []
    missing_requirements: List[str] = []

    if preview_status != "ready" or lock_quality != LOCK_QUALITY_STABLE:
        missing_requirements.append("当前锁定对象还不够稳定")
    if action_type == "sql_preview" and not target_table:
        missing_requirements.append("缺少明确的目标表名")
    if operation_type in {"select", "update", "delete"} and not predicate_bindings:
        missing_requirements.append("缺少可复核的 WHERE 条件")
    if operation_type == "insert" and not safe_field_bindings:
        missing_requirements.append("缺少可写入的字段绑定")
    if operation_type == "update" and not assignment_bindings:
        missing_requirements.append("缺少明确的更新字段和值")

    sql_ready = not missing_requirements and bool(target_table or action_type != "sql_preview")
    sql_preview_text = ""
    if sql_ready and target_table:
        quoted_table = _quote_sql_identifier(target_table)
        predicates_sql = [
            f"{_quote_sql_identifier(_binding_label(item))} = {_quote_sql_literal(_binding_value(item))}"
            for item in predicate_bindings
            if _binding_label(item)
        ]
        if operation_type == "select":
            sql_preview_text = (
                f"SELECT *\n"
                f"FROM {quoted_table}\n"
                f"WHERE {' AND '.join(predicates_sql)}\n"
                f"LIMIT 20;"
            )
        elif operation_type == "insert":
            columns = [_binding_label(item) for item in safe_field_bindings if _binding_label(item)]
            values = [_quote_sql_literal(_binding_value(item)) for item in safe_field_bindings if _binding_label(item)]
            if columns and values:
                sql_preview_text = (
                    f"INSERT INTO {quoted_table} (\n"
                    f"  {', '.join(_quote_sql_identifier(column) for column in columns)}\n"
                    f")\n"
                    f"VALUES (\n"
                    f"  {', '.join(values)}\n"
                    f");"
                )
        elif operation_type == "update":
            assignments_sql = [
                f"{_quote_sql_identifier(str(item.get('label') or item.get('field_name') or '字段'))} = {_quote_sql_literal(item.get('value'))}"
                for item in assignment_bindings
            ]
            if assignments_sql and predicates_sql:
                sql_preview_text = (
                    f"UPDATE {quoted_table}\n"
                    f"SET {', '.join(assignments_sql)}\n"
                    f"WHERE {' AND '.join(predicates_sql)};"
                )
        elif operation_type == "delete" and predicates_sql:
            sql_preview_text = (
                f"DELETE FROM {quoted_table}\n"
                f"WHERE {' AND '.join(predicates_sql)};"
            )

    sql_ready = bool(sql_preview_text)
    evidence_basis = {
        "focus_scope": str(preview_payload.get("focus_scope") or ""),
        "table_id": str(preview_payload.get("table_id") or ""),
        "page": preview_payload.get("page"),
        "row_index": preview_payload.get("row_index"),
        "source_row_index": preview_payload.get("source_row_index"),
        "identifier_fields": [
            {
                "label": _binding_label(item),
                "value": _binding_value(item),
                "ref_id": str(item.get("source_ref_id") or ""),
            }
            for item in predicate_bindings[:3]
            if _binding_label(item)
        ],
    }
    confirmation_checklist = _build_confirmation_checklist(
        operation_type,
        target_table=target_table,
        table_status=table_status,
        sql_ready=sql_ready,
        missing_requirements=missing_requirements,
    )
    return {
        "operation_type": operation_type,
        "target_table": target_table,
        "target_table_status": table_status,
        "sql_ready": sql_ready,
        "sql_preview_text": sql_preview_text,
        "assignment_bindings": assignment_bindings[:6],
        "confirmation_checklist": confirmation_checklist,
        "missing_requirements": missing_requirements[:6],
        "affected_scope": _describe_affected_scope(operation_type, preview_payload),
        "evidence_basis": evidence_basis,
    }


def build_action_preview(
    user_message: str,
    document: DocumentExtractionResponse,
    matched_fields: List[Dict[str, Any]],
    *,
    payload: Optional[Dict[str, Any]] = None,
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    action_id = f"action-{uuid.uuid4().hex}"
    text = str(user_message or "").strip()
    field_names = [str(item.get("field_name") or "") for item in matched_fields if str(item.get("field_name") or "").strip()]
    action_type = "sql_preview" if any(hint in text.lower() for hint in SQL_HINTS) else "save_preview"
    title = "数据库动作预览"
    description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。"
    target = "Data_Extraction"
    preview_payload: Dict[str, Any] = {
        "file_hash": document.file_hash,
        "file_name": document.file_name,
        "matched_fields": field_names[:12],
        "user_instruction": text,
        "preview_status": "ready",
        "lock_quality": LOCK_QUALITY_NONE,
    }

    anchor_terms = _extract_row_anchor_terms(text)
    explicit_row_index = _extract_explicit_row_number(text)
    has_direct_row_signal = bool(anchor_terms or explicit_row_index or _followup_row_query(text))
    assessment = (
        assess_table_lookup(
            document=document,
            payload=payload or {},
            user_message=text,
            current_object_lock=current_object_lock,
        )
        if has_direct_row_signal
        else {}
    )

    preview_table = None
    preview_row = None
    preview_reason = ""
    preview_lock_quality = LOCK_QUALITY_NONE
    blocked_candidates = assessment.get("candidate_rows") if isinstance(assessment.get("candidate_rows"), list) else []

    if bool(assessment.get("resolved")) and str(assessment.get("lock_quality") or "") == LOCK_QUALITY_STABLE:
        preview_table, preview_row, preview_reason, preview_lock_quality = _resolve_preview_row(
            payload or {},
            matched_fields,
            current_object_lock=assessment.get("current_object_lock") if isinstance(assessment.get("current_object_lock"), dict) else current_object_lock,
        )
        preview_reason = "current_table_row_lock" if bool(assessment.get("used_context_lock")) else "query_row_grounding"
        preview_lock_quality = LOCK_QUALITY_STABLE
    elif not has_direct_row_signal:
        preview_table, preview_row, preview_reason, preview_lock_quality = _resolve_preview_row(
            payload or {},
            matched_fields,
            current_object_lock=current_object_lock,
        )

    current_lock_type = str(current_object_lock.get("lock_type") or "").strip().lower() if current_object_lock else ""
    current_lock_quality = str(current_object_lock.get("lock_quality") or "").strip().lower() if current_object_lock else ""
    current_lock_quality = current_lock_quality or LOCK_QUALITY_STABLE
    current_lock_metadata = current_object_lock.get("metadata") if current_object_lock and isinstance(current_object_lock.get("metadata"), dict) else {}

    if preview_table and preview_row and preview_lock_quality == LOCK_QUALITY_STABLE:
        page = int(preview_table.get("page", 0) or 0) or None
        row_bindings = _build_row_field_bindings(preview_row, matched_fields, page)
        if row_bindings:
            preview_payload["matched_fields"] = [
                str(item.get("field_name") or item.get("label") or "")
                for item in row_bindings
                if str(item.get("field_name") or item.get("label") or "").strip()
            ][:12]
            preview_payload["field_bindings"] = row_bindings
        preview_payload.update(
            {
                "preview_status": "ready",
                "lock_quality": LOCK_QUALITY_STABLE,
                "focus_scope": "table_row",
                "focus_reason": preview_reason or "row_context",
                "table_id": str(preview_table.get("table_id") or ""),
                "page": page,
                "row_index": int(preview_row.get("row_index", 0) or 0) or None,
                "source_row_index": int(preview_row.get("source_row_index", 0) or 0) or None,
                "row_preview": _row_preview(preview_row, max_cells=12),
            }
        )
        if preview_reason == "current_table_row_lock":
            description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。本次预览沿用了当前稳定锁定的表格行。"
        else:
            description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。本次预览基于当前问题中新明确锁定的表格行。"
    elif current_lock_type == "ocr_fact_group" and current_lock_quality == LOCK_QUALITY_STABLE and not has_direct_row_signal:
        fact_fields = current_lock_metadata.get("fact_fields") if isinstance(current_lock_metadata.get("fact_fields"), list) else []
        fact_preview = current_lock_metadata.get("fact_preview") if isinstance(current_lock_metadata.get("fact_preview"), list) else []
        if fact_fields:
            preview_payload["field_bindings"] = fact_fields[:6]
            preview_payload["matched_fields"] = [
                str(item.get("field_name") or item.get("label") or "")
                for item in fact_fields[:6]
                if isinstance(item, dict) and str(item.get("field_name") or item.get("label") or "").strip()
            ][:12]
        preview_payload.update(
            {
                "preview_status": "ready",
                "lock_quality": LOCK_QUALITY_STABLE,
                "focus_scope": "ocr_fact_group",
                "focus_reason": "current_ocr_fact_group_lock",
                "focus_lock": dict(current_object_lock or {}),
                "fact_items": fact_preview[:6],
            }
        )
        description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。本次预览沿用了当前稳定的 OCR 事实组，而不是把它误当成 figure 级对象。"
    else:
        if not blocked_candidates and preview_table and preview_row:
            weak_candidate = _build_row_candidate(
                table=preview_table,
                row=preview_row,
                query=text,
                anchor_terms=anchor_terms,
                explicit_row_index=explicit_row_index,
                preferred_header=str(current_lock_metadata.get("header") or ""),
                match_reason=preview_reason or "matched_field_row_cluster",
                force_score=1,
            )
            if weak_candidate:
                blocked_candidates = [_summarize_row_candidate(weak_candidate, 1)]
        preview_payload.update(
            {
                "preview_status": "blocked",
                "lock_quality": str(assessment.get("lock_quality") or preview_lock_quality or LOCK_QUALITY_NONE),
                "focus_scope": "unresolved_table_row" if blocked_candidates else (current_lock_type or "context"),
                "focus_reason": str(assessment.get("clarification_reason") or preview_reason or "unresolved_context"),
                "candidate_rows": blocked_candidates[:3],
                "clarification_question": "请补充准确的行号、站点名称、编码，或直接回复候选编号 1/2/3 后我再继续生成预览。",
            }
        )
        if current_object_lock:
            preview_payload["focus_lock"] = dict(current_object_lock)
        description = (
            "当前阶段已识别到数据库相关意图，但目标对象仍不是 stable_lock。"
            "为了避免把弱关联行或模糊上下文误绑定到数据库动作，本次预览已阻塞，只保留确认信息，不会继续生成可执行绑定。"
        )

    action_details = _build_database_action_details(
        user_message=text,
        action_type=action_type,
        preview_payload=preview_payload,
    )
    preview_payload.update(action_details)
    if action_type == "sql_preview":
        if bool(action_details.get("sql_ready")):
            description = description + " 目前已经整理出可确认的 SQL 预览，但仍不会自动执行。"
        else:
            description = description + " 当前只完成了来源记录绑定与安全检查，最终 SQL 预览还缺少必要条件。"

    return {
        "action_id": action_id,
        "action_type": action_type,
        "title": title,
        "description": description,
        "target": target,
        "requires_confirmation": True,
        "payload": preview_payload,
    }


def enrich_matched_fields_with_trace_hits(
    matched_fields: List[Dict[str, Any]],
    trace_hits: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    exact_lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_field: Dict[str, Dict[str, Any]] = {}
    by_ref: Dict[str, Dict[str, Any]] = {}
    for hit in trace_hits:
        if not isinstance(hit, dict):
            continue
        object_id = str(hit.get("object_id") or "").strip().lower()
        ref_id = str(hit.get("ref_id") or "").strip()
        if object_id and ref_id:
            exact_lookup[(object_id, ref_id)] = hit
        if object_id and object_id not in by_field:
            by_field[object_id] = hit
        if ref_id and ref_id not in by_ref:
            by_ref[ref_id] = hit

    enriched: List[Dict[str, Any]] = []
    for item in matched_fields:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        field_name = str(next_item.get("field_name") or next_item.get("label") or "").strip().lower()
        ref_id = str(next_item.get("source_ref_id") or "").strip()
        hit = exact_lookup.get((field_name, ref_id)) or by_field.get(field_name) or by_ref.get(ref_id)
        if isinstance(hit, dict):
            if next_item.get("page") is None and hit.get("page") is not None:
                next_item["page"] = hit.get("page")
            snippet = str(hit.get("snippet") or "").strip()
            if snippet:
                source_excerpt = snippet.split("|", 1)[1].strip() if "|" in snippet else snippet
                if source_excerpt:
                    next_item["source_excerpt"] = source_excerpt[:240]
        enriched.append(next_item)
    return enriched


def build_field_citations(matched_fields: List[Dict[str, Any]], trace_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    exact_lookup = {
        (str(hit.get("object_id") or "").strip().lower(), str(hit.get("ref_id") or "").strip()): hit
        for hit in trace_hits
        if isinstance(hit, dict) and str(hit.get("object_id") or "").strip() and str(hit.get("ref_id") or "").strip()
    }
    by_field = {
        str(hit.get("object_id") or "").strip().lower(): hit
        for hit in trace_hits
        if isinstance(hit, dict) and str(hit.get("object_id") or "").strip()
    }
    by_ref = {
        str(hit.get("ref_id") or ""): hit
        for hit in trace_hits
        if isinstance(hit, dict) and str(hit.get("ref_id") or "").strip()
    }
    citations: List[Dict[str, Any]] = []
    for item in matched_fields[:6]:
        field_name = str(item.get("field_name") or item.get("label") or "").strip()
        ref_id = str(item.get("source_ref_id") or "").strip()
        hit = exact_lookup.get((field_name.lower(), ref_id)) or by_field.get(field_name.lower()) or by_ref.get(ref_id)
        page = item.get("page")
        if page is None and isinstance(hit, dict):
            page = hit.get("page")
        citations.append(
            {
                "citation_type": "field",
                "title": str(item.get("label") or item.get("field_name") or "字段"),
                "page": page,
                "ref_id": ref_id or None,
                "object_id": field_name,
                "snippet": str((hit or {}).get("snippet") or item.get("source_excerpt") or item.get("value") or "")[:300],
                "payload": {
                    "field_name": field_name,
                    "label": str(item.get("label") or ""),
                    "value": item.get("value"),
                    "confidence": float(item.get("confidence", 0.0) or 0.0),
                    "page": page,
                    "source_excerpt": str(item.get("source_excerpt") or "")[:240],
                },
            }
        )
    return citations


def build_action_preview_citations(action_preview: Dict[str, Any]) -> List[Dict[str, Any]]:
    preview = action_preview if isinstance(action_preview, dict) else {}
    payload = preview.get("payload") if isinstance(preview.get("payload"), dict) else {}
    bindings = payload.get("field_bindings") if isinstance(payload.get("field_bindings"), list) else []
    citations: List[Dict[str, Any]] = []
    for item in bindings[:6]:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field_name") or item.get("label") or "").strip()
        label = str(item.get("label") or field_name or "字段").strip()
        value = item.get("value")
        ref_id = str(item.get("source_ref_id") or "").strip() or None
        citations.append(
            {
                "citation_type": "field",
                "title": label,
                "page": item.get("page") or payload.get("page"),
                "ref_id": ref_id,
                "object_id": field_name or label,
                "snippet": f"{label}: {value}",
                "payload": {
                    "field_name": field_name or label,
                    "label": label,
                    "value": value,
                    "confidence": item.get("confidence"),
                    "page": item.get("page") or payload.get("page"),
                    "table_id": payload.get("table_id"),
                    "row_index": payload.get("row_index"),
                    "source_row_index": payload.get("source_row_index"),
                },
            }
        )
    return citations


def _focus_label(current_focus: Dict[str, Any]) -> str:
    if not isinstance(current_focus, dict) or not current_focus:
        return ""
    quality_raw = str(current_focus.get("lock_quality") or "").strip().lower()
    quality_map = {
        LOCK_QUALITY_STABLE: "定位已经比较稳定",
        LOCK_QUALITY_WEAK: "定位还有一点浮动",
        LOCK_QUALITY_NONE: "还没有完全锁稳",
    }
    subject = _focus_subject(current_focus)
    if not subject:
        return ""
    return f"你现在追问的是{subject}，{quality_map.get(quality_raw, '当前定位状态还需要再确认')}。"


def _find_preview_cell(preview_cells: List[Dict[str, Any]], *header_candidates: str) -> Optional[Dict[str, Any]]:
    normalized_candidates = [str(candidate).strip() for candidate in header_candidates if str(candidate).strip()]
    for candidate in normalized_candidates:
        for cell in preview_cells:
            if not isinstance(cell, dict):
                continue
            header = str(cell.get("header") or "").strip()
            if header == candidate:
                return cell
    for cell in preview_cells:
        if not isinstance(cell, dict):
            continue
        header = str(cell.get("header") or "").strip()
        if not header:
            continue
        if any(candidate in header for candidate in normalized_candidates):
            return cell
    return None


def _looks_like_internal_locator(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return bool(
        re.search(
            r"(?i)(?:^xlsx_|^docx_|^pptx_|^pdf_|^img_|^table[_\-]?\d+|^figure[_\-]?\d+|"
            r"_r\d+_c\d+|^fig[_\-]?\d+|^tbl[_\-]?\d+)",
            value,
        )
    )


def _focus_subject(current_focus: Dict[str, Any]) -> str:
    if not isinstance(current_focus, dict) or not current_focus:
        return ""

    row_label = str(current_focus.get("row_label") or "").strip()
    if row_label and not _looks_like_internal_locator(row_label) and not re.fullmatch(r"\d{5,}", row_label):
        return f"“{row_label}”这条记录"

    row_preview = current_focus.get("row_preview") if isinstance(current_focus.get("row_preview"), list) else []
    for header_candidates in (
        ("站点名称", "站点", "监测点", "站名"),
        ("名称", "对象名称", "项目名称"),
        ("标题", "caption", "title"),
        ("地区", "城市", "区域"),
        ("时间", "监测时间", "日期"),
    ):
        cell = _find_preview_cell(row_preview, *header_candidates)
        text = str((cell or {}).get("text") or "").strip()
        if text and not _looks_like_internal_locator(text):
            return f"“{text}”这条记录"

    header = str(current_focus.get("header") or "").strip()
    if header and not _looks_like_internal_locator(header):
        return f"当前围绕“{header}”命中的结果"

    label = str(current_focus.get("label") or "").strip()
    if label and not _looks_like_internal_locator(label):
        return f"“{label}”这个对象"

    lock_type = str(current_focus.get("lock_type") or "").strip().lower()
    return {
        "table_row": "当前锁定的这条表格记录",
        "ocr_fact_group": "当前锁定的这组 OCR 事实",
        "figure": "当前锁定的图表对象",
        "field": "当前命中的字段结果",
    }.get(lock_type, "当前锁定的对象")


def _natural_candidate_label(candidate: Dict[str, Any]) -> str:
    if not isinstance(candidate, dict):
        return "当前这个候选对象"

    row_label = str(candidate.get("row_label") or "").strip()
    if row_label and not _looks_like_internal_locator(row_label) and not re.fullmatch(r"\d{5,}", row_label):
        return f"“{row_label}”这条记录"

    best_cell_value = str(candidate.get("best_cell_value") or "").strip()
    if best_cell_value and not _looks_like_internal_locator(best_cell_value):
        return f"包含“{best_cell_value}”的那条记录"

    matched_terms = [str(item).strip() for item in candidate.get("matched_anchor_terms") or [] if str(item).strip()]
    if matched_terms:
        return f"与“{'、'.join(matched_terms[:2])}”最接近的那条记录"

    return "当前这个候选记录"


def _overview_counts_text(overview: Dict[str, Any]) -> str:
    if not isinstance(overview, dict):
        return ""
    field_count = int(overview.get("field_count", 0) or 0)
    stable_field_count = int(overview.get("stable_field_count", 0) or 0)
    unstable_field_count = int(overview.get("unstable_field_count", 0) or 0)
    table_count = int(overview.get("table_count", 0) or 0)
    figure_count = int(overview.get("figure_count", 0) or 0)
    if field_count <= 0 and table_count <= 0 and figure_count <= 0:
        return ""
    if field_count <= 0 and figure_count <= 0 and table_count > 0:
        table_label = "一张表" if table_count == 1 else f"{table_count} 张表"
        return f"当前已经能稳定看到{table_label}，后续追问问题不大，但字段级映射还没完全收紧。"

    parts: List[str] = []
    if field_count > 0:
        if stable_field_count > 0 and unstable_field_count > 0:
            parts.append("字段结果已经开始成形了，但里面还有待复核项")
        elif unstable_field_count > 0:
            parts.append("字段结果已经出来了一部分，不过还在继续收紧")
        else:
            parts.append("字段结果已经比较成形了")
    elif table_count > 0 or figure_count > 0:
        parts.append("结构化结果已经开始成形了")

    if table_count > 0:
        parts.append("表格对象这边已经能稳定引用")
    if figure_count > 0:
        parts.append("图片或图表这边也拿到了一部分可引用结果")
    return "；".join(parts) + "。"


def _looks_like_risk_review_question(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    lowered = text.lower()
    risk_tokens = (
        "风险",
        "异常",
        "问题",
        "核对",
        "复核",
        "排查",
        "优先",
        "注意",
        "容易出错",
        "判断点",
        "检查",
        "坑",
    )
    return "risk" in lowered or any(token in text for token in risk_tokens)


def _document_summary_priority_checks(overview: Dict[str, Any]) -> List[str]:
    if not isinstance(overview, dict):
        return []

    checks: List[str] = []
    current_focus = overview.get("current_focus") if isinstance(overview.get("current_focus"), dict) else {}
    row_preview = current_focus.get("row_preview") if isinstance(current_focus.get("row_preview"), list) else []
    preview_cells = [item for item in row_preview if isinstance(item, dict)]
    focus_quality = str(current_focus.get("lock_quality") or "").strip().lower()

    if focus_quality == LOCK_QUALITY_STABLE and preview_cells:
        anchor_bits: List[str] = []
        used_headers: set[str] = set()
        for header_candidates in (("站点名称", "站点"), ("站点编码", "编码"), ("监测时间", "时间")):
            cell = _find_preview_cell(preview_cells, *header_candidates)
            if not cell:
                continue
            header = str(cell.get("header") or "").strip()
            text = str(cell.get("text") or "").strip()
            if not header or header in used_headers:
                continue
            if header and text:
                anchor_bits.append(f"{header}={text}")
                used_headers.add(header)
        if anchor_bits:
            checks.append("先核对当前锁定行的关键锚点是否一致：" + "；".join(anchor_bits[:3]) + "。")
        checks.append("再核对你后续要引用或入库的值列，是否确实来自这一条已锁定记录，而不是只命中了同页或同表里的相似数值。")
        pm10_cell = _find_preview_cell(preview_cells, "PM10")
        if pm10_cell:
            checks.append(
                "当前行里已经能看到 PM10 这一列，下一步最好顺手核对它与污染类型、监测时间是否属于同一行上下文，避免列错位后答对数字、答错对象。"
            )

    field_count = int(overview.get("field_count", 0) or 0)
    table_count = int(overview.get("table_count", 0) or 0)
    if table_count > 0 and field_count <= 0:
        checks.append("这张表已经能继续追问了，但字段到业务字段的映射还没完全收紧，正式入库前最好再过一遍列名对应关系。")

    warnings = [
        str(item).strip()
        for item in (overview.get("soft_warnings") if isinstance(overview.get("soft_warnings"), list) else [])
        if str(item).strip() and str(item).strip().lower() != "quality_gate_ok"
    ]
    if warnings:
        checks.append("当前还有这些软告警值得优先复核：" + "；".join(warnings[:3]) + "。")

    return checks[:4]


def fallback_answer(route: str, answer_context: Dict[str, Any]) -> str:
    route_key = str(route or "").strip().lower()
    if route_key == "table_lookup":
        value = str(answer_context.get("value") or "").strip()
        used_lock = bool(answer_context.get("used_context_lock"))
        current_focus = (
            answer_context.get("current_object_lock")
            if isinstance(answer_context.get("current_object_lock"), dict)
            else {}
        )
        focus_subject = _focus_subject(current_focus)
        context_line = (
            "沿着刚才那条记录继续看，我这次就按同一条数据往下答。"
            if used_lock
            else f"这次我就按{focus_subject or '这条记录'}来答，先给你稳定值。"
        )
        next_step = (
            "要继续看这条记录，直接点指标名就行。"
            if value
            else "要继续确认的话，我可以顺着这条记录把相关字段再往下捋一遍。"
        )
        return f"{value or '当前值为空'}。{context_line}{next_step}".strip()

    if route_key in {"figure_overview", "figure_value_read"}:
        figures = answer_context.get("figures") if isinstance(answer_context.get("figures"), list) else []
        recognition_tier = str(answer_context.get("recognition_tier") or "").strip() or "none"
        prefer_field_facts = bool(answer_context.get("prefer_field_facts"))
        fallback_fields = answer_context.get("fallback_fields") if isinstance(answer_context.get("fallback_fields"), list) else []
        fallback_tables = answer_context.get("fallback_tables") if isinstance(answer_context.get("fallback_tables"), list) else []
        if not figures:
            if prefer_field_facts and fallback_fields:
                tier_label = (
                    "OCR / 字段级（还不是稳定的图表对象）"
                    if recognition_tier == "ocr_field_only"
                    else "OCR / 表格级（还不是稳定的图表对象）"
                    if recognition_tier == "ocr_table_only"
                    else "当前还没有形成稳定的图表层级结果"
                )
                lines = [
                    "这轮我还不能把当前内容当成一个稳定的图表对象来回答，不过已经能先给你一组较可靠的字段级事实。",
                    "",
                    f"当前识别层级：{tier_label}。",
                    "",
                    "目前能直接引用的内容有：",
                ]
                for item in fallback_fields[:6]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(
                        f"- {str(item.get('label') or item.get('field_name') or '字段')}: "
                        f"{str(item.get('value') or '')}"
                    )
                lines.extend(
                    [
                        "",
                        "换句话说，现在更适合把它当成字段事实继续追问，"
                        "还不适合直接把它说成稳定的整图结论。",
                    ]
                )
                return "\n".join(lines).strip()
            if fallback_tables:
                lines = [
                    "当前还没有稳定到可以把整张图片或图表当成完整对象来回答，"
                    "但我已经拿到了可用的表格布局线索，所以可以先按行列去理解它。",
                    "",
                    f"当前识别层级：{'OCR / 表格级（非稳定图表级）' if recognition_tier == 'ocr_table_only' else '尚未形成稳定图表对象'}。",
                    "",
                    "目前可引用的表格线索如下：",
                ]
                for table in fallback_tables[:2]:
                    if not isinstance(table, dict):
                        continue
                    row_count = table.get("row_count") or "未知"
                    col_count = table.get("col_count") or "未知"
                    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
                    lines.append(f"- 当前已经识别出一个可继续追问的表格结构，大致有 {row_count} 行、{col_count} 列。")
                    if headers:
                        lines.append(f"  表头线索：{'；'.join([str(item) for item in headers[:4]])}")
                    preview_rows = table.get("preview_rows") if isinstance(table.get("preview_rows"), list) else []
                    for row in preview_rows[:2]:
                        if not isinstance(row, dict):
                            continue
                        cells = row.get("cells") if isinstance(row.get("cells"), list) else []
                        cell_text = " | ".join(
                            f"{str(cell.get('header') or 'col')}={str(cell.get('text') or '')}"
                            for cell in cells[:4]
                            if isinstance(cell, dict) and str(cell.get("text") or "").strip()
                        )
                        if cell_text:
                            lines.append(f"  其中一条记录示例：{cell_text}")
                lines.extend(
                    [
                        "",
                        "换句话说，这张内容现在更适合按表格里的字段和记录继续追问，"
                        "而不是直接按完整图表对象来追问。",
                    ]
                )
                return "\n".join(lines).strip()
            if fallback_fields:
                lines = [
                    "当前还没有形成稳定的图表对象，所以我不想把回答说得过满。",
                    "",
                    f"当前识别层级：{'OCR / 字段级（非稳定图表级）' if recognition_tier == 'ocr_field_only' else '尚未形成稳定图表对象'}。",
                    "",
                    "不过我已经拿到了一批可作为参考的字段级结果：",
                ]
                for item in fallback_fields[:4]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(
                        f"- {str(item.get('label') or item.get('field_name') or '字段')}: "
                        f"{str(item.get('value') or '')}"
                    )
                lines.extend(
                    [
                        "",
                        "这说明当前识别还停留在 OCR / 字段级，距离稳定的图标题、关键要点或 dataframe 级结果还有一点距离。",
                    ]
                )
                return "\n".join(lines).strip()
            return (
                "这轮我还没有拿到足够稳定的图表对象信息，所以现在不能负责任地给出图表级结论。"
                "\n\n更稳的做法是先按标题、局部文字片段，或者表格里的字段和记录继续收窄。"
            )
        lines = [
            "我先把当前能稳定识别到的图表对象整理给你。"
            if route_key == "figure_overview"
            else "目前已经能锁定到图表对象，不过如果你要继续精确读取数值，最好再点明具体内容区域或你想看的指标。",
            "",
        ]
        for item in figures[:6]:
            caption = str(item.get("caption") or item.get("title") or "未命名图表")
            key_points = item.get("key_points") if isinstance(item.get("key_points"), list) else []
            dataframe_rows = item.get("dataframe_rows") if isinstance(item.get("dataframe_rows"), list) else []
            lines.append(f"- {caption}")
            if key_points:
                lines.append(f"  当前关键要点：{'；'.join([str(x) for x in key_points[:3]])}")
            else:
                lines.append("  当前关键要点：暂时还没有稳定提炼出来。")
            if dataframe_rows:
                lines.append("  结构化程度：已经识别到局部 dataframe 行。")
            else:
                lines.append("  结构化程度：还没有稳定到 dataframe 级。")
        return "\n".join(lines).strip()

    if route_key == "knowledge_explain":
        question = str(answer_context.get("user_question") or "").strip()
        document_overview = answer_context.get("document_overview") if isinstance(answer_context.get("document_overview"), dict) else {}
        overview_text = _overview_counts_text(document_overview)
        question_lower = question.lower()
        doc_bridge = ""
        if "ocr" in question_lower and any(token in question for token in ("版面", "布局", "版面分析", "布局分析", "区别")):
            lines = [
                "先把这两个东西分开。OCR 和版面分析，管的不是一回事。",
                "",
                "OCR 主要看“这块区域里写了什么字”，重点是把扫描件、图片或截图里的文字认出来；"
                "版面分析看的是“这些内容在页面上怎么组织”，比如标题、正文、表格、图片、页眉页脚、脚注之间是什么关系。",
                "",
                "之所以一定要把两者分开，是因为只做 OCR 往往只能拿到字面文本，"
                "但阅读顺序、列关系、表头归属、跨行跨列这些真正影响语义的结构信息很容易丢。"
                "更稳一点的做法是先把页面区域和阅读顺序理出来，再决定哪些区域走 OCR、哪些区域走表格恢复、哪些区域走图片理解。",
                "",
                "你可以先粗一点理解成：OCR 更像“认字”，版面分析更像“把页面关系理顺”。"
                "真到实际处理里，很多错不在单个字，而在这个值到底还归不归原来那一行、那一列。",
            ]
            doc_bridge = "拿你现在这份表来说，真正要盯的不是某个字认得像不像，而是每个值有没有回到对的行和列里。"
        elif any(token in question for token in ("表格恢复", "表格抽取", "表格识别", "单元格", "跨行", "跨列")):
            lines = [
                "表格抽取得好不好，关键不只是把字认出来，更关键的是行列关系有没有还原对。",
                "",
                "比较稳的做法是：先找出页面里哪里是表格，再恢复单元格网格，接着做单元格文本识别，"
                "最后把多级表头、合并单元格、跨行跨列关系补回来，让每个值都能落到明确的行和列上。",
                "",
                "最容易翻车的一般不在 OCR 本身，而在结构恢复这一步："
                "比如表头换行、多层标题、单位写在表头而不是单元格、截图表格没有明显边线、表格被图片压得很糊。"
                "这里只要歪一次，后面的字段绑定、入库和问答基本都会跟着漂。",
                "",
                "所以别只看“识别出多少字”，还要看“这个值到底属于哪一行、哪一列、哪一个表头语义”。"
                "这也是为什么表格问答一定要强调上下文锁定，不能只凭一个相似数字就往下答。",
            ]
            doc_bridge = "放到你当前这份文档里，这一步最值得盯的是表头归属、行列对齐，以及同一条记录能不能连续追问而不漂。"
        elif (
            any(token in question_lower for token in ("sql", "nl2sql"))
            or any(token in question for token in ("数据库", "增删改查"))
            or (
                any(token in question for token in ("入库", "落库"))
                and any(token in question_lower for token in ("sql", "where", "insert", "update", "delete"))
            )
            or (
                any(token in question for token in ("入库", "落库"))
                and any(token in question for token in ("字段映射", "目标表", "审计", "权限", "回滚"))
            )
        ):
            lines = [
                "把文档内容落库，难点不在 SQL 会不会写，而在落进去的东西是不是清楚、可追溯、可审计。",
                "",
                "比较稳的链路就这几步：先做文档解析和字段/表格/图片取证，再做字段标准化和校验，"
                "然后生成数据库动作预览，等用户确认之后再执行，最后把执行前后差异和证据引用一起记进审计日志。",
                "",
                "自然语言转 SQL 也不能裸奔。比较合理的约束包括：限定允许操作的表、默认先预览再执行、"
                "对 update/delete 强制要求 where 条件和影响范围预估、禁止无条件写操作、把模型输出和最终执行 SQL 分开记录。"
                "不然模型很容易把含糊表达直接翻成高风险动作。",
                "",
                "简单说，好的 NL2SQL 不是“让模型直接写库”，而是“让模型先给候选动作，再用规则、确认和审计把风险压下来”。",
            ]
            doc_bridge = "拿你现在这份文档说，表格已经能继续追问，不代表字段映射和入库条件已经完全稳定，所以中间这层预览、确认和审计不能省。"
        else:
            lines = [
                "别把非结构化文档处理看成一个单点能力，它更像一条分层流水线。",
                "",
                "前半段处理“看懂文档”：包括文件解析、OCR、版面分析、表格恢复、图片和图表理解、阅读顺序恢复；"
                "中间层处理“把事实组织起来”：例如字段抽取、值和来源片段绑定、行列锚定、图表对象建模、置信度评估；"
                "后半段处理“让结果可用”：例如问答、检索、入库、SQL 操作预览、审计与回溯。",
                "",
                "真会影响体验的，不是某个模型单点有多强，而是证据链有没有闭合。"
                "用户问一个值时，系统最好不仅能回答值，还能说清这个值是不是已经锁稳、能不能继续追问、后续能不能安全入库。",
                "",
                "所以要是你希望助手既能回答文档内容，又能帮用户理解方法论，比较稳的做法是把“抽取事实”和“解释知识”分成两种回答模式，"
                "但共用同一份文档上下文和证据能力。",
            ]
            doc_bridge = "落到你当前这份文档上，最关键的还是先把可追问对象锁稳，再去谈问答、入库和后续操作。"
        if overview_text and not doc_bridge:
            doc_bridge = f"拿你当前这份文档说，{overview_text}"
        if doc_bridge:
            lines.append("")
            lines.append(doc_bridge)
        lines.append("")
        lines.append("真要把它做稳，先守住两条线：证据别漂，执行别越界。")
        return "\n".join(lines).strip()

    if route_key == "document_summary":
        question = str(answer_context.get("user_question") or "").strip()
        current_focus = answer_context.get("current_focus") if isinstance(answer_context.get("current_focus"), dict) else {}
        focus_line = _focus_label(current_focus)
        overview_text = _overview_counts_text(answer_context)
        summary_text = str(answer_context.get("summary_text") or "").strip() or "暂无摘要。"
        evidence_scope = str(answer_context.get("evidence_scope") or "").strip().rstrip("。；; ")
        priority_checks = _document_summary_priority_checks(answer_context)
        if _looks_like_risk_review_question(question):
            lines = ["这份表我会先盯这几件事。"]
            if focus_line:
                lines.extend(["", focus_line])
            if priority_checks:
                lines.append("")
                for item in priority_checks:
                    lines.append(f"- {item}")
            elif overview_text:
                lines.extend(["", overview_text])
            lines.extend(["", "如果你接下来要做人工复核或准备入库，我建议先按“对象锁定、列对齐、字段映射”这个顺序过一遍。"])
            return "\n".join(lines).strip()

        lines = ["先说我现在能比较稳地确认的部分。"]
        if focus_line:
            lines.extend(["", focus_line])
        if summary_text and summary_text != "暂无摘要。":
            lines.extend(["", f"整体看，这份文档主要在讲：{summary_text}"])
            if overview_text:
                lines.extend(["", f"就解析进度来说，{overview_text}"])
        else:
            if overview_text:
                lines.extend(["", overview_text])
            lines.extend(["", "现在还没有足够完整的整文摘要，所以这轮更适合作局部概览，不适合直接当成全量复盘。"])
            if priority_checks:
                lines.extend(["", "如果你接下来要继续深挖，我会先盯这几件事："])
                for item in priority_checks[:3]:
                    lines.append(f"- {item}")
        if evidence_scope:
            lines.extend(["", f"这轮判断主要还是基于当前已经抽出来的结果，范围大致在：{evidence_scope}。"])
        return "\n".join(lines).strip()

    if route_key == "database_action":
        preview = answer_context.get("action_preview") if isinstance(answer_context.get("action_preview"), dict) else {}
        payload = preview.get("payload") if isinstance(preview.get("payload"), dict) else {}
        preview_status = str(payload.get("preview_status") or "ready")
        lock_quality = str(payload.get("lock_quality") or LOCK_QUALITY_NONE)
        target = str(preview.get("target") or "未指定").strip() or "未指定"
        action_type = str(preview.get("action_type") or "").strip().lower()
        operation_type = str(payload.get("operation_type") or "").strip().lower()
        target_table = str(payload.get("target_table") or "").strip()
        table_status = str(payload.get("target_table_status") or "").strip().lower()
        sql_ready = bool(payload.get("sql_ready"))
        sql_preview_text = str(payload.get("sql_preview_text") or "").strip()
        affected_scope = str(payload.get("affected_scope") or "").strip()
        missing_requirements = payload.get("missing_requirements") if isinstance(payload.get("missing_requirements"), list) else []
        confirmation_checklist = payload.get("confirmation_checklist") if isinstance(payload.get("confirmation_checklist"), list) else []
        evidence_basis = payload.get("evidence_basis") if isinstance(payload.get("evidence_basis"), dict) else {}
        identifier_fields = evidence_basis.get("identifier_fields") if isinstance(evidence_basis.get("identifier_fields"), list) else []
        operation_label = {
            "select": "查询",
            "insert": "写入",
            "update": "更新",
            "delete": "删除",
        }.get(operation_type, "数据库")
        lock_quality_label = {
            LOCK_QUALITY_STABLE: "稳定锁定",
            LOCK_QUALITY_WEAK: "弱锁定",
            LOCK_QUALITY_NONE: "未形成稳定锁定",
        }.get(lock_quality, lock_quality or "未形成稳定锁定")
        table_status_line = ""
        if target_table:
            table_status_line = (
                f"目标表是 {target_table}。"
                + (" 这张表当前已在白名单内。" if table_status == "whitelisted" else " 这张表目前还不在白名单内，正式执行前还需要补齐表级校验。")
            )
        if preview_status == "blocked":
            lines = [
                "我已经把你的数据库请求整理成了动作预览，但这一步现在还不能安全继续。",
                "",
                f"当前目标是 {target}，但现有绑定还停留在“{lock_quality_label}”这个阶段，所以我先把它拦在确认之前。",
            ]
            if identifier_fields:
                lines.extend(
                    [
                        "",
                        "目前已经能复核的定位条件有："
                        + "；".join(
                            f"{str(item.get('label') or '字段')}={str(item.get('value') or '')}"
                            for item in identifier_fields[:3]
                            if isinstance(item, dict)
                        )
                        + "。",
                    ]
                )
            if missing_requirements:
                lines.extend(["", "现在卡住的关键原因是：" + "；".join(str(item) for item in missing_requirements[:4]) + "。"])
            candidate_rows = payload.get("candidate_rows") if isinstance(payload.get("candidate_rows"), list) else []
            if candidate_rows:
                lines.extend(["", "我先把最可能的候选记录列给你，你确认后我再继续："])
                for item in candidate_rows[:3]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(f"- 候选 {item.get('rank') or '?'}：{_natural_candidate_label(item)}。")
            clarification_question = str(payload.get("clarification_question") or "").strip()
            lines.extend(
                [
                    "",
                    clarification_question or "你可以先确认目标记录、表名或主键条件；对象一旦确认下来，我就能继续给你更稳的动作预览。",
                ]
            )
            return "\n".join(lines).strip()
        field_bindings = payload.get("field_bindings") if isinstance(payload.get("field_bindings"), list) else []
        lines = [
            f"我已经把这次 {operation_label} 请求整理成可确认的数据库预览了，但现在还只是预览，不会直接执行真实写操作。",
            "",
            f"现在已经到了可以继续确认的预览阶段，目标数据库是 {target}，当前绑定强度是 {lock_quality_label}。",
        ]
        if table_status_line:
            lines.extend(["", table_status_line])
        if affected_scope:
            lines.extend(["", affected_scope])
        if field_bindings:
            lines.extend(["", "这次预览里已经绑定到的关键字段包括："])
            for item in field_bindings[:4]:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {str(item.get('label') or item.get('field_name') or '字段')}: {str(item.get('value') or '')}")
        if sql_ready and sql_preview_text:
            lines.extend(["", "SQL 预览如下：", sql_preview_text])
        elif action_type == "sql_preview":
            lines.extend(
                [
                    "",
                    "我已经把来源对象和关键字段绑定好了，但最终 SQL 还没到可执行预览这一步。",
                ]
            )
            if missing_requirements:
                lines.append("还缺少的条件是：" + "；".join(str(item) for item in missing_requirements[:4]) + "。")
            else:
                lines.append("如果你再补充目标表名、更新字段或更明确的筛选条件，我就能继续给出完整 SQL。")
        if confirmation_checklist:
            lines.extend(["", "在你确认之前，建议优先核对这几件事："])
            for item in confirmation_checklist[:4]:
                lines.append(f"- {str(item)}")
        lines.extend(
            [
                "",
                "如果你确认目标对象和字段绑定没有问题，我下一步可以继续进入严格确认和审计流程，再决定是否执行。",
            ]
        )
        return "\n".join(lines).strip()

    if route_key == "web_research":
        document_overview = answer_context.get("document_overview") if isinstance(answer_context.get("document_overview"), dict) else {}
        overview_text = _overview_counts_text(document_overview)
        summary_text = str(answer_context.get("summary_text") or "").strip()
        live_web_result_available = bool(answer_context.get("live_web_result_available"))
        lines = [
            "可以，我先把边界拆开说。",
            "",
            "先说文档里现在能确认的部分。",
        ]
        if overview_text:
            lines.append(overview_text)
        else:
            lines.append("基于当前这份文档，我可以先帮你做抽取、核对和解释，但这不等于已经拿到了外部最新规范。")
        if summary_text:
            lines.extend(["", f"如果只看这份材料，它当前更像是在讲：{summary_text}"])
        lines.extend(
            [
                "",
                "再说通用经验。对这类数据处理任务，通常会重点盯数据来源、时间粒度、字段单位、异常值处理和入库前复核这些环节。",
                "",
                "最后是必须联网再核的部分。凡是你问“最新规范”“最新政策”“最近最佳实践”这类问题，我都建议重新查外部来源，"
                "而且最好把来源、发布时间和链接一起带上。",
            ]
        )
        if not live_web_result_available:
            lines.extend(
                [
                    "",
                    "所以这轮我能负责的是先把文档内证据和通用做法讲清楚；凡是涉及“最新”的判断，我会明确告诉你还差联网核验。",
                ]
            )
        return "\n".join(lines).strip()

    if route_key == "field_lookup":
        fields = answer_context.get("matched_fields") if isinstance(answer_context.get("matched_fields"), list) else []
        if not fields:
            return "这轮我还没有稳定匹配到你要找的字段。你可以直接告诉我字段名、别名，或者点名想看的表格 / 图片对象，我再帮你往下收窄。"
        first = fields[0] if isinstance(fields[0], dict) else {}
        label = str(first.get("label") or first.get("field_name") or "字段").strip() or "字段"
        value = str(first.get("value") or "").strip()
        return (
            f"{label}的值是“{value}”。\n\n"
            "我这次是按当前已经命中的字段结果来回答的。"
            "如果你担心有同名字段混在一起，我也可以把相近候选并排列出来给你比对。"
        ).strip()

    if route_key == "clarification_needed":
        clarification_reason = str(answer_context.get("clarification_reason") or "").strip()
        if clarification_reason in {"followup_without_locked_row", "no_matching_row", "anchor_terms_unresolved", "candidate_ambiguity", "weak_row_grounding"}:
            candidate_rows = answer_context.get("candidate_rows") if isinstance(answer_context.get("candidate_rows"), list) else []
            missing_anchor_terms = answer_context.get("missing_anchor_terms") if isinstance(answer_context.get("missing_anchor_terms"), list) else []
            lines = [
                "我已经尽量顺着你当前的问题去找目标记录了，但这轮还不能稳定锁定到唯一的一条记录。",
                "",
            ]
            if missing_anchor_terms:
                lines.append(f"目前最缺的是更明确的行锚点，尤其是：{'、'.join([str(item) for item in missing_anchor_terms[:4] if str(item).strip()])}。")
            else:
                lines.append("当前目标对象还没有稳定锁定，如果我继续硬答，存在把错误记录当成目标对象的风险。")
            if candidate_rows:
                lines.extend(["", "我先把最接近的候选列出来，你确认其中一个，我就能继续往下答："])
                for item in candidate_rows[:3]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(f"- 候选 {item.get('rank') or '?'}：{_natural_candidate_label(item)}。")
            lines.extend(
                [
                    "",
                    "你可以直接回复“候选 1 / 2 / 3”，或者再补一个更具体的站点名称、编码、字段线索，我就能继续往下读。",
                ]
            )
            return "\n".join(lines).strip()
        document_overview = answer_context.get("document_overview") if isinstance(answer_context.get("document_overview"), dict) else {}
        overview_text = _overview_counts_text(document_overview)
        lines = [
            "我已经尽量利用当前文档上下文去理解你的问题了，但这轮还缺少足够稳定的直接证据，所以不想冒然给你一个看起来完整、实际上不稳的答案。",
        ]
        if overview_text:
            lines.extend(["", overview_text])
        lines.extend(
            [
                "",
                "你可以再指定得更具体一点，比如字段名、表名、标题文字，或者直接贴出你想核对的那句话，我会继续帮你收窄到可引用的对象。",
            ]
        )
        return "\n".join(lines).strip()

    return (
        "我已经尽量利用现有文档上下文去组织回答了，但当前能直接引用的证据还不够稳定。"
        "你可以继续告诉我更具体的字段、表格、图片对象或想核对的值，我会按这个方向继续往下找。"
    )


def _compact_context_for_model(
    value: Any,
    *,
    max_depth: int,
    max_list_items: int,
    max_dict_items: int,
    max_string_chars: int,
) -> Any:
    if max_depth <= 0:
        if isinstance(value, list):
            return {"truncated": True, "item_count": len(value)}
        if isinstance(value, dict):
            return {"truncated": True, "key_count": len(value)}
        text = str(value or "")
        return text[:max_string_chars]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[: max(1, max_dict_items)]:
            out[str(key)] = _compact_context_for_model(
                item,
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
                max_string_chars=max_string_chars,
            )
        if len(items) > max_dict_items:
            out["_truncated_keys"] = len(items) - max_dict_items
        return out
    if isinstance(value, list):
        out_list = [
            _compact_context_for_model(
                item,
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
                max_string_chars=max_string_chars,
            )
            for item in value[: max(1, max_list_items)]
        ]
        if len(value) > max_list_items:
            out_list.append({"_truncated_items": len(value) - max_list_items})
        return out_list
    if isinstance(value, str):
        return value[: max(32, max_string_chars)]
    return value


def dump_context_for_model(value: Dict[str, Any]) -> Dict[str, Any]:
    max_chars = max(1500, int(os.getenv("MODULE2_ASSISTANT_CONTEXT_JSON_MAX_CHARS", "12000")))
    max_depth = max(2, int(os.getenv("MODULE2_ASSISTANT_CONTEXT_MAX_DEPTH", "6")))
    max_list_items = max(2, int(os.getenv("MODULE2_ASSISTANT_CONTEXT_MAX_LIST_ITEMS", "8")))
    max_dict_items = max(4, int(os.getenv("MODULE2_ASSISTANT_CONTEXT_MAX_DICT_ITEMS", "24")))
    max_string_chars = max(120, int(os.getenv("MODULE2_ASSISTANT_CONTEXT_MAX_STRING_CHARS", "1200")))

    raw_value: Any = value if isinstance(value, dict) else {"text": str(value)}
    compacted = _compact_context_for_model(
        raw_value,
        max_depth=max_depth,
        max_list_items=max_list_items,
        max_dict_items=max_dict_items,
        max_string_chars=max_string_chars,
    )
    try:
        serialized = json.dumps(compacted, ensure_ascii=False)
    except Exception:
        return {"text": str(raw_value)[:max_chars]}
    if len(serialized) <= max_chars:
        return compacted if isinstance(compacted, dict) else {"value": compacted}

    tighter = _compact_context_for_model(
        raw_value,
        max_depth=max(2, max_depth - 2),
        max_list_items=max(2, min(max_list_items, 4)),
        max_dict_items=max(4, min(max_dict_items, 12)),
        max_string_chars=max(120, min(max_string_chars, 480)),
    )
    try:
        tighter_serialized = json.dumps(tighter, ensure_ascii=False)
    except Exception:
        return {"text": str(raw_value)[:max_chars]}
    if len(tighter_serialized) <= max_chars:
        return tighter if isinstance(tighter, dict) else {"value": tighter}
    return {
        "context_truncated": True,
        "context_preview": tighter_serialized[:max_chars],
        "context_chars": len(tighter_serialized),
    }
