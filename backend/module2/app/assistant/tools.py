from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import DocumentExtractionResponse


PERSIST_HINTS = ("入库", "落库", "保存", "存储", "写入数据库", "写库", "数据库")
SQL_HINTS = ("sql", "查询数据库", "更新数据库", "删除数据", "新增数据", "select ", "insert ", "update ", "delete ")
WEB_HINTS = ("联网", "搜索", "查一下", "最新", "最近", "政策", "法规", "新闻", "web", "google", "bing")
FIGURE_HINTS = ("图", "图表", "图片", "chart", "figure", "figure_id", "关键要点", "dataframe", "坐标轴", "趋势")
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
    text = re.split(r"[，。；、,.;!?？\s]", text, maxsplit=1)[0].strip()
    text = text.rstrip("的").strip()
    return text if len(_normalize_text(text)) >= 2 else ""


def _extract_row_anchor_terms(query: str) -> List[str]:
    text = str(query or "").strip()
    if not text:
        return []
    patterns = (
        r"(?:站点名称|站点|监测点|站名)\s*(?:为|是|叫|=|:|：)?\s*([A-Za-z0-9\u4e00-\u9fff\-_\.]{2,40})",
        r"(?:城市|地区|区域|区县)\s*(?:为|是|叫|=|:|：)?\s*([A-Za-z0-9\u4e00-\u9fff\-_\.]{2,40})",
        r"(?:学校|企业|机构)\s*(?:为|是|叫|=|:|：)?\s*([A-Za-z0-9\u4e00-\u9fff\-_\.]{2,40})",
        r"(?:编号|编码|序号)\s*(?:为|是|=|:|：)?\s*([A-Za-z0-9\-_\.]{2,40})",
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


def _row_anchor_match_score(row: Dict[str, Any], anchor_terms: List[str]) -> int:
    if not anchor_terms:
        return 0
    score = 0
    for term in anchor_terms:
        best = 0
        for cell in row.get("cells", []):
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            if not text:
                continue
            if _contains_text(term, text):
                best = max(best, min(18, len(_normalize_text(term)) + 6))
            score += best
    return score


def _has_explicit_row_locator(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    return bool(re.search(r"(?:第\s*\d+\s*行|row\s*\d+)", text, flags=re.IGNORECASE))


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

    if any(hint in text for hint in SQL_HINTS) or any(hint in text for hint in PERSIST_HINTS):
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
    metadata = current_object_lock.get("metadata") if isinstance(current_object_lock.get("metadata"), dict) else {}

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
        return {
            "lock_type": lock_type or "table_row",
            "label": str(current_object_lock.get("label") or current_object_lock.get("object_id") or resolved_table_id or "当前对象"),
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
        "label": str(current_object_lock.get("label") or current_object_lock.get("object_id") or "当前对象"),
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


def _resolve_preview_row(
    payload: Dict[str, Any],
    matched_fields: List[Dict[str, Any]],
    current_object_lock: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    if current_object_lock:
        lock_type = str(current_object_lock.get("lock_type") or "").strip().lower()
        if lock_type == "table_row":
            table, row = _find_row_by_lock(payload, current_object_lock)
            if table and row:
                return table, row, "current_table_row_lock"
        lock_ref_id = current_object_lock.get("ref_id")
        if lock_ref_id:
            table, row = _find_row_by_ref_id(payload, lock_ref_id)
            if table and row:
                return table, row, "current_lock_ref"

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
        return None, None, ""

    best_group = max(
        by_group.items(),
        key=lambda pair: (
            float(pair[1].get("score", 0.0) or 0.0),
            str(pair[0]),
        ),
    )
    table, row = _find_row_by_ref_id(payload, best_group[1].get("ref_id"))
    if table and row:
        return table, row, "matched_field_row_cluster"
    return None, None, ""


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
    query = str(user_message or "").strip()
    anchor_terms = _extract_row_anchor_terms(query)
    explicit_row_locator = _has_explicit_row_locator(query)
    has_row_lock = bool(
        current_object_lock
        and str(current_object_lock.get("lock_type", "")).lower() == "table_row"
    )
    if _followup_row_query(query) and not has_row_lock and not anchor_terms and not explicit_row_locator:
        return None
    locked_table = None
    locked_row = None
    if current_object_lock and str(current_object_lock.get("lock_type", "")).lower() == "table_row" and _followup_row_query(query):
        locked_table, locked_row = _find_row_by_lock(payload, current_object_lock)

    candidate_rows: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    if locked_table is not None and locked_row is not None:
        candidate_rows.append((999, locked_table, locked_row))
    else:
        for table in _table_payloads(payload):
            table_id = str(table.get("table_id") or "").strip()
            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue
                score = _keyword_overlap_score(query, table_id)
                if anchor_terms:
                    anchor_score = _row_anchor_match_score(row, anchor_terms)
                    if anchor_score <= 0:
                        continue
                    score += anchor_score
                for cell in row.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    cell_text = str(cell.get("text") or "").strip()
                    if len(cell_text) >= 2:
                        if _contains_text(query, cell_text):
                            score += min(18, len(_normalize_text(cell_text)) + 4)
                    score += min(8, _header_score(str(cell.get("header") or ""), query))
                if score > 0:
                    candidate_rows.append((score, table, row))
    if not candidate_rows:
        return None

    candidate_rows.sort(key=lambda item: item[0], reverse=True)
    table = candidate_rows[0][1]
    row = candidate_rows[0][2]

    best_cell = None
    best_cell_score = -1
    preferred_header = str(current_object_lock.get("metadata", {}).get("header") or "") if current_object_lock else ""
    for cell in row.get("cells", []):
        if not isinstance(cell, dict):
            continue
        header = str(cell.get("header") or "").strip()
        text = str(cell.get("text") or "").strip()
        score = _header_score(header, query)
        if preferred_header and header and _normalize_text(header) == _normalize_text(preferred_header):
            score += 2
        if _contains_text(query, text):
            score += 2
        if score > best_cell_score:
            best_cell_score = score
            best_cell = cell

    if best_cell is None:
        return None
    if best_cell_score <= 0 and not locked_row:
        return None

    table_id = str(table.get("table_id") or "")
    trace_hit = _find_trace_hit(document, "table", table_id)
    page = int(table.get("page", 0) or 0) or int((trace_hit or {}).get("page", 0) or 0) or None
    row_index = int(row.get("row_index", 0) or 0) or None
    source_row_index = int(row.get("source_row_index", 0) or 0) or row_index
    ref_id = str(best_cell.get("ref_id") or "").strip() or None
    value = str(best_cell.get("text") or "").strip()
    header = str(best_cell.get("header") or "").strip()
    row_label = ""
    for cell in row.get("cells", []):
        if not isinstance(cell, dict):
            continue
        text = str(cell.get("text") or "").strip()
        if text:
            row_label = text
            break
    citation = {
        "citation_type": "table",
        "title": f"表格 {table_id}",
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
            "row_preview": _row_preview(row),
            "artifact_url": str((trace_hit or {}).get("artifact_url") or ""),
            "artifact_path": str((trace_hit or {}).get("artifact_path") or ""),
        },
    }
    current_lock = {
        "lock_type": "table_row",
        "object_id": table_id,
        "label": f"{table_id} 第{row_index or '?'}行",
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
        "used_context_lock": bool(locked_row is not None),
    }


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
    }

    preview_table, preview_row, preview_reason = _resolve_preview_row(
        payload or {},
        matched_fields,
        current_object_lock=current_object_lock,
    )
    if preview_table and preview_row:
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
            description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。本次预览优先沿用了当前锁定的表格行。"
        else:
            description = "当前阶段已识别到数据库相关意图。这里先生成预览，不会直接执行真实写操作。本次预览优先采用了与当前问题最相关的表格行。"
    elif current_object_lock:
        preview_payload["focus_scope"] = str(current_object_lock.get("lock_type") or "context").strip() or "context"
        preview_payload["focus_lock"] = dict(current_object_lock)

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


def fallback_answer(route: str, answer_context: Dict[str, Any]) -> str:
    route_key = str(route or "").strip().lower()
    if route_key == "table_lookup":
        value = str(answer_context.get("value") or "").strip()
        table_id = str(answer_context.get("table_id") or "").strip()
        page = answer_context.get("page")
        row_index = answer_context.get("row_index")
        source_row_index = answer_context.get("source_row_index")
        ref_id = str(answer_context.get("ref_id") or "").strip()
        used_lock = bool(answer_context.get("used_context_lock"))
        context_line = "本轮沿用了上一轮锁定的同一行上下文。" if used_lock else "本轮根据当前问题重新定位到了目标行。"
        return (
            f"结论：当前定位到的值为“{value}”。\n\n"
            f"依据：表格 {table_id}，第 {page or '?'} 页，表内第 {row_index or '?'} 行，"
            f"原始第 {source_row_index or '?'} 行，ref_id：{ref_id or '未识别'}。\n\n"
            f"补充说明：{context_line}"
        ).strip()

    if route_key in {"figure_overview", "figure_value_read"}:
        figures = answer_context.get("figures") if isinstance(answer_context.get("figures"), list) else []
        recognition_tier = str(answer_context.get("recognition_tier") or "").strip() or "none"
        fallback_tables = answer_context.get("fallback_tables") if isinstance(answer_context.get("fallback_tables"), list) else []
        if not figures:
            if fallback_tables:
                lines = [
                    "结论：当前还没有建立稳定的图表对象，因此暂时不能给出可靠的 figure_id / 页码级图表结论。",
                    "",
                    f"当前识别层级：{'OCR / 表格级（非 figure 级）' if recognition_tier == 'ocr_table_only' else '未形成稳定 figure 级结果'}。",
                    "",
                    "依据：不过当前图片里已经识别到可引用的表格布局对象，可以先按表格行列来理解内容：",
                ]
                for table in fallback_tables[:2]:
                    if not isinstance(table, dict):
                        continue
                    table_id = str(table.get("table_id") or "未命名表格")
                    page = table.get("page") or "未知"
                    row_count = table.get("row_count") or "未知"
                    col_count = table.get("col_count") or "未知"
                    headers = table.get("headers") if isinstance(table.get("headers"), list) else []
                    lines.append(
                        f"- 表格 {table_id}（page={page}，行数={row_count}，列数={col_count}）"
                    )
                    if headers:
                        lines.append(f"  表头线索：{'；'.join([str(item) for item in headers[:4]])}")
                    preview_rows = table.get("preview_rows") if isinstance(table.get("preview_rows"), list) else []
                    for row in preview_rows[:2]:
                        if not isinstance(row, dict):
                            continue
                        row_label = f"表内第 {row.get('row_index') or '?'} 行"
                        cells = row.get("cells") if isinstance(row.get("cells"), list) else []
                        cell_text = " | ".join(
                            f"{str(cell.get('header') or 'col')}={str(cell.get('text') or '')}"
                            for cell in cells[:4]
                            if isinstance(cell, dict) and str(cell.get("text") or "").strip()
                        )
                        if cell_text:
                            lines.append(f"  {row_label}：{cell_text}")
                lines.append("")
                lines.append("补充说明：这说明当前更适合继续按表格对象、行列或 ref_id 追问，而不是按 figure_id 追问。")
                return "\n".join(lines).strip()
            fallback_fields = answer_context.get("fallback_fields") if isinstance(answer_context.get("fallback_fields"), list) else []
            if fallback_fields:
                lines = [
                    "结论：当前还没有建立稳定的图表对象，因此暂时不能给出可靠的 figure_id / 页码级图表结论。",
                    "",
                    f"当前识别层级：{'OCR / 字段级（非 figure 级）' if recognition_tier == 'ocr_field_only' else '未形成稳定 figure 级结果'}。",
                    "",
                    "依据：不过我已经拿到一批 OCR / 字段级结果，可以先作为当前识别效果的补充参考：",
                ]
                for item in fallback_fields[:4]:
                    if not isinstance(item, dict):
                        continue
                    lines.append(
                        f"- {str(item.get('label') or item.get('field_name') or '字段')}: "
                        f"{str(item.get('value') or '')} "
                        f"(ref_id={str(item.get('source_ref_id') or '未知')}, page={item.get('page') or '未知'})"
                    )
                lines.append("")
                lines.append("补充说明：这说明当前识别层级更接近 OCR / 字段级，还没有稳定进入 figure 标题级、关键要点级或 dataframe 级。")
                return "\n".join(lines).strip()
            return "结论：当前没有拿到稳定的图表对象信息，因此还不能给出可靠的图表概述。\n\n补充说明：当前识别层级仍停留在“未识别”而不是 figure 级。"
        lines = ["结论：当前文档中已识别到以下图表对象。", ""]
        for item in figures[:6]:
            figure_id = str(item.get("figure_id") or "")
            page = item.get("page")
            caption = str(item.get("caption") or item.get("title") or figure_id)
            key_points = item.get("key_points") if isinstance(item.get("key_points"), list) else []
            dataframe_rows = item.get("dataframe_rows") if isinstance(item.get("dataframe_rows"), list) else []
            lines.append(f"- {caption}（figure_id={figure_id}，页码={page or '未知'}）")
            if key_points:
                lines.append(f"  当前关键要点：{'；'.join([str(x) for x in key_points[:3]])}")
            else:
                lines.append("  当前关键要点：暂未稳定识别到。")
            if dataframe_rows:
                lines.append("  dataframe：已识别到局部结构化行。")
            else:
                lines.append("  dataframe：暂未稳定识别到。")
        return "\n".join(lines).strip()

    if route_key == "document_summary":
        current_focus = answer_context.get("current_focus") if isinstance(answer_context.get("current_focus"), dict) else {}
        focus_line = ""
        if current_focus:
            focus_bits = [
                str(current_focus.get("label") or "").strip(),
                f"第 {current_focus.get('page')} 页" if current_focus.get("page") else "",
                f"表内第 {current_focus.get('row_index')} 行" if current_focus.get("row_index") else "",
                f"原始第 {current_focus.get('source_row_index')} 行" if current_focus.get("source_row_index") else "",
            ]
            focus_line = "当前锁定对象：" + "，".join([bit for bit in focus_bits if bit]) + "。\n\n"
        return (
            f"结论：我先基于当前文档已解析出的结构化结果做一个概览。\n\n"
            f"{focus_line}"
            f"目前已识别字段 {int(answer_context.get('field_count', 0) or 0)} 个，"
            f"其中稳定字段 {int(answer_context.get('stable_field_count', 0) or 0)} 个、"
            f"仍需谨慎核对的字段 {int(answer_context.get('unstable_field_count', 0) or 0)} 个；"
            f"表格 {int(answer_context.get('table_count', 0) or 0)} 个、"
            f"图表 {int(answer_context.get('figure_count', 0) or 0)} 个。\n\n"
            f"依据范围：{str(answer_context.get('evidence_scope') or '当前概览主要来自现有结构化抽取结果。')}\n\n"
            f"摘要：{str(answer_context.get('summary_text') or '暂无摘要')}"
        ).strip()

    if route_key == "database_action":
        preview = answer_context.get("action_preview") if isinstance(answer_context.get("action_preview"), dict) else {}
        return (
            "结论：我已经识别到这是一个数据库动作意图。\n\n"
            "补充说明：当前先生成了动作预览，不会直接执行真实写操作。"
            f"\n目标：{str(preview.get('target') or '未指定')}"
        ).strip()

    if route_key == "field_lookup":
        fields = answer_context.get("matched_fields") if isinstance(answer_context.get("matched_fields"), list) else []
        if not fields:
            return "当前没有稳定匹配到目标字段。你可以告诉我更明确的字段名、别名，或者直接指出想看的表格/图表对象。"
        first = fields[0] if isinstance(fields[0], dict) else {}
        return (
            f"结论：当前最稳定命中的字段是“{str(first.get('label') or first.get('field_name') or '字段')}”，"
            f"值为“{str(first.get('value') or '')}”。\n\n"
            f"依据：页码 {first.get('page') or '未知'}，ref_id：{str(first.get('source_ref_id') or '未识别')}。"
        ).strip()

    return (
        "当前我已经尽量利用现有文档上下文进行了判断，但还缺少足够稳定的直接证据。"
        "如果你愿意，可以再指定目标对象，例如某个字段、某张表、某个 figure_id，或者直接指出你想核对的值。"
    )


def dump_context_for_model(value: Dict[str, Any]) -> Dict[str, Any]:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return {"text": str(value)}
