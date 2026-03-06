from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.agent.graph import AgentState, ExtractionGraph
from app.core.office_pdf import convert_word_bytes_to_pdf, is_word_file
from app.core.parser import parse_document_in_subprocess
from app.db.storage import ExtractionStorage
from app.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    BatchExtractionResponse,
    BridgeJobCreateRequest,
    BridgeJobStatusRequest,
    BridgeTraceLocateRequest,
    CacheClearResponse,
    DocumentExtractionResponse,
    ExtractionResult,
    SummarizeRequest,
    SummarizeResponse,
    TraceLocateRequest,
    TraceLocateResponse,
)


@dataclass
class RouteDecision:
    file_hash: str
    cache_key: str
    track: str
    cached_payload: Optional[Dict[str, Any]]


@dataclass
class BridgeJobState:
    job_id: str
    request_id: str
    status: str
    created_at: float
    updated_at: float
    total_files: int
    completed_files: int
    failed_files: int
    file_names: List[str]
    documents: List[DocumentExtractionResponse]
    errors: List[str]

    def terminal(self) -> bool:
        return self.status in {"completed", "failed"}


@dataclass
class OfficePreviewJob:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    file_name: str
    file_hash: str
    artifact_path: Optional[str]
    artifact_url: Optional[str]
    error: str = ""


class StreamRouter:
    """Layer 1: Ingestion & triage (hash/cache/routing)."""

    def __init__(self, storage: ExtractionStorage) -> None:
        self.storage = storage

    async def triage(self, file_name: str, file_bytes: bytes, schema_hash: str) -> RouteDecision:
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        cache_key = hashlib.sha256(f"{file_hash}:{schema_hash}".encode("utf-8")).hexdigest()
        cached = await self.storage.check_cache(cache_key)
        if cached:
            return RouteDecision(file_hash=file_hash, cache_key=cache_key, track="CacheHit", cached_payload=cached)

        if not file_name.lower().endswith(".pdf"):
            return RouteDecision(file_hash=file_hash, cache_key=cache_key, track="FastTrack", cached_payload=None)

        force_visual = (os.getenv("MODULE2_PDF_FORCE_VISUAL", "true") or "true").lower() in {"1", "true", "yes"}
        if force_visual:
            track = "VisualTrack"
        else:
            is_native = self._is_native_pdf(file_name, file_bytes)
            track = "FastTrack" if is_native else "VisualTrack"
        return RouteDecision(file_hash=file_hash, cache_key=cache_key, track=track, cached_payload=None)

    @staticmethod
    def _is_native_pdf(file_name: str, file_bytes: bytes) -> bool:
        if not file_name.lower().endswith(".pdf"):
            return False

        sample = file_bytes[:200000]
        has_text_ops = b"BT" in sample and b"ET" in sample
        has_font = b"/Font" in sample
        image_heavy = sample.count(b"/Image") > 20
        return has_text_ops and has_font and not image_heavy


def _cors_origins() -> tuple[List[str], bool]:
    raw = os.getenv(
        "MODULE2_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:3002,http://localhost:5173",
    )
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        origins = ["http://localhost:3000"]
    allow_all = "*" in origins
    return origins, allow_all


def _max_workers() -> int:
    cpu = os.cpu_count() or 4
    return min(max(cpu - 1, 2), 8)


process_pool = ProcessPoolExecutor(max_workers=_max_workers())

app = FastAPI(title="A23 Module 2 - Unstructured Document Extraction", version="1.0.0")
CORS_ORIGINS, CORS_ALLOW_ALL = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = ExtractionStorage(os.getenv("MODULE2_DATABASE_DSN", "postgresql://postgres:postgres@localhost:5432/a23"))
graph = ExtractionGraph()
bridge_jobs: Dict[str, BridgeJobState] = {}
bridge_request_index: Dict[str, str] = {}
bridge_lock = asyncio.Lock()
office_preview_jobs: Dict[str, OfficePreviewJob] = {}
office_preview_lock = asyncio.Lock()


def _schema_hash(schema: Dict[str, Any]) -> str:
    normalized = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _schema_target_fields(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    fields = schema.get("fields")
    if isinstance(fields, dict):
        return dict(fields)
    excluded = {"dependencies", "validations", "required", "auto_infer", "max_auto_fields", "prefer_llm"}
    return {str(k): v for k, v in schema.items() if str(k) not in excluded}


def _schema_auto_infer_requested(schema: Dict[str, Any]) -> bool:
    if not isinstance(schema, dict):
        return True
    if bool(schema.get("auto_infer")):
        return True
    return len(_schema_target_fields(schema)) == 0


def _coerce_field_type(type_hint: Any) -> str:
    text = str(type_hint or "").strip().lower()
    if text in {"number", "float", "int", "integer", "numeric", "decimal", "ratio", "percent"}:
        return "number"
    if text in {"date", "datetime", "time", "timestamp"}:
        return "string"
    return "string"


def _sanitize_field_name(raw_name: Any) -> str:
    text = re.sub(r"\s+", " ", str(raw_name or "").strip())
    if not text:
        return ""
    text = re.sub(r"[^\w\u4e00-\u9fff ]+", "", text)
    text = text.strip()
    if len(text) < 2:
        return ""
    return text[:48]


def _normalize_schema_fields(fields: Dict[str, Any], max_fields: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, type_hint in fields.items():
        key = _sanitize_field_name(name)
        if not key or key in out:
            continue
        out[key] = _coerce_field_type(type_hint)
        if len(out) >= max_fields:
            break
    return out


def _extract_text_for_schema(markdown: str, table_blocks: List[Dict[str, Any]], max_chars: int = 16000) -> str:
    compact_md = _TAG_RE.sub(" ", str(markdown or ""))
    compact_md = re.sub(r"\s+", " ", compact_md).strip()
    table_headers: List[str] = []
    for table in table_blocks[:10]:
        headers = table.get("headers")
        if not isinstance(headers, list):
            continue
        for item in headers[:10]:
            head = str(item or "").strip()
            if head:
                table_headers.append(head)
    merged = f"{compact_md}\n表头：{' | '.join(table_headers)}".strip()
    if len(merged) > max_chars:
        merged = merged[:max_chars]
    return merged


def _field_name_prefers_number(field_name: str) -> bool:
    text = str(field_name or "").strip().lower()
    if not text:
        return False
    zh_tokens = (
        "金额",
        "数量",
        "总量",
        "总数",
        "总计",
        "合计",
        "均值",
        "平均",
        "比例",
        "占比",
        "比率",
        "税率",
        "增速",
        "增长率",
        "成本",
        "费用",
        "单价",
        "率",
        "值",
    )
    en_tokens = (
        "amount",
        "total",
        "count",
        "number",
        "num",
        "quantity",
        "ratio",
        "rate",
        "percent",
        "price",
        "cost",
        "value",
        "score",
        "index",
    )
    return any(tok in text for tok in zh_tokens) or any(tok in text for tok in en_tokens)


def _infer_schema_fields_heuristic(markdown: str, table_blocks: List[Dict[str, Any]], max_fields: int) -> Dict[str, str]:
    stop_tokens = {
        "ref",
        "page",
        "table",
        "figure",
        "sheet",
        "id",
        "text",
        "name",
        "字段",
        "内容",
        "序号",
        "备注",
        "说明",
    }
    score_map: Dict[str, int] = {}
    type_map: Dict[str, str] = {}

    def push_candidate(raw_name: Any, score: int) -> None:
        key = _sanitize_field_name(raw_name)
        if not key:
            return
        lower_key = key.lower()
        if lower_key in stop_tokens:
            return
        if len(key) <= 2 and not re.search(r"[\u4e00-\u9fff]", key):
            return
        prev_score = score_map.get(key, 0)
        if score > prev_score:
            score_map[key] = score
        inferred = "number" if _field_name_prefers_number(key) else "string"
        prev_type = type_map.get(key)
        if prev_type is None or (prev_type != "number" and inferred == "number"):
            type_map[key] = inferred

    for table_idx, table in enumerate(table_blocks[:12], start=1):
        base_score = max(20, 140 - table_idx * 8)
        headers = table.get("headers")
        if isinstance(headers, list):
            for col_idx, header in enumerate(headers[:24], start=1):
                push_candidate(header, base_score - col_idx)

        header_meta = table.get("header_meta")
        if isinstance(header_meta, list):
            for item in header_meta[:24]:
                if not isinstance(item, dict):
                    continue
                push_candidate(item.get("name"), base_score + 4)
                unit = str(item.get("unit", "") or "").strip()
                if unit:
                    push_candidate(f"{item.get('name')}_{unit}", base_score)

    plain = _TAG_RE.sub(" ", str(markdown or ""))
    plain = re.sub(r"\s+", " ", plain)
    if plain:
        kv_pattern = re.compile(
            r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff()（）\-/·]{1,40})\s*[:：]\s*[^:：\n]{1,80}"
        )
        seen_hits: Dict[str, int] = {}
        for match in kv_pattern.finditer(plain[:32000]):
            candidate = _sanitize_field_name(match.group(1))
            if not candidate:
                continue
            seen_hits[candidate] = seen_hits.get(candidate, 0) + 1
        for name, hit_count in seen_hits.items():
            push_candidate(name, 90 + min(18, hit_count * 4))

    if not score_map:
        return {}

    ranked = sorted(
        score_map.keys(),
        key=lambda name: (
            -score_map.get(name, 0),
            0 if type_map.get(name) == "number" else 1,
            len(name),
            name,
        ),
    )
    out: Dict[str, str] = {}
    for name in ranked:
        out[name] = type_map.get(name, "string")
        if len(out) >= max_fields:
            break
    return out


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    if fenced.startswith("{") and fenced.endswith("}"):
        try:
            payload = json.loads(fenced)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    match = re.search(r"\{[\s\S]*\}", fenced)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


async def _infer_schema_fields_llm(
    *,
    file_name: str,
    markdown: str,
    table_blocks: List[Dict[str, Any]],
    max_fields: int,
) -> Dict[str, str]:
    llm = getattr(graph, "llm", None)
    if llm is None:
        return {}

    is_xlsx = file_name.lower().endswith(".xlsx")
    context = _extract_text_for_schema(markdown, table_blocks, max_chars=4200 if is_xlsx else 9000)
    if not context:
        return {}

    system_prompt = (
        "你是文档抽取字段规划器。请根据文档内容给出最有价值、可定位的抽取字段。"
        "仅返回 JSON，不要输出解释文本。字段数量控制在 4-12 个。"
    )
    user_prompt = (
        f"文件名：{file_name}\n"
        f"上下文：\n{context}\n\n"
        "输出格式：\n"
        "{\n"
        '  "fields": [\n'
        '    {"field_name": "字段名", "field_type": "string|number"},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
    )

    try:
        invoke_coro = llm.ainvoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        raw_resp = await asyncio.wait_for(invoke_coro, timeout=max(6.0, float(os.getenv("MODULE2_AUTO_SCHEMA_LLM_TIMEOUT_SEC", "16"))))
    except Exception:
        return {}

    content_raw: Any = getattr(raw_resp, "content", raw_resp)
    if isinstance(content_raw, list):
        chunks: List[str] = []
        for item in content_raw:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    chunks.append(text)
            else:
                text = str(item or "").strip()
                if text:
                    chunks.append(text)
        content_text = "\n".join(chunks).strip()
    else:
        content_text = str(content_raw or "").strip()

    payload = _extract_json_payload(content_text)
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        return {}

    parsed: Dict[str, str] = {}
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        field_name = _sanitize_field_name(item.get("field_name"))
        if not field_name or field_name in parsed:
            continue
        parsed[field_name] = _coerce_field_type(item.get("field_type"))
        if len(parsed) >= max_fields:
            break
    return parsed


async def _resolve_effective_schema(
    *,
    requested_schema: Dict[str, Any],
    file_name: str,
    markdown: str,
    table_blocks: List[Dict[str, Any]],
    profile_hint: str = "",
    allow_llm: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    req_fields = _schema_target_fields(requested_schema)
    max_fields = max(4, min(int(requested_schema.get("max_auto_fields", 12) or 12), 20))
    if file_name.lower().endswith(".xlsx") or str(profile_hint).lower() == "table_heavy":
        max_fields = min(max_fields, 6)
    auto_infer = _schema_auto_infer_requested(requested_schema)
    if not auto_infer:
        normalized = _normalize_schema_fields(req_fields, max_fields=max_fields)
        effective = dict(requested_schema)
        effective["fields"] = normalized
        return effective, {
            "mode": "manual",
            "source": "request",
            "field_count": len(normalized),
            "fields": list(normalized.keys()),
        }

    llm_enabled = bool(requested_schema.get("prefer_llm", True)) and bool(allow_llm)
    llm_fields: Dict[str, str] = {}
    if llm_enabled:
        llm_fields = await _infer_schema_fields_llm(
            file_name=file_name,
            markdown=markdown,
            table_blocks=table_blocks,
            max_fields=max_fields,
        )
    heuristic_fields = _infer_schema_fields_heuristic(markdown=markdown, table_blocks=table_blocks, max_fields=max_fields)

    merged: Dict[str, str] = {}
    for source in (llm_fields, heuristic_fields):
        for name, type_hint in source.items():
            key = _sanitize_field_name(name)
            if not key or key in merged:
                continue
            merged[key] = _coerce_field_type(type_hint)
            if len(merged) >= max_fields:
                break
        if len(merged) >= max_fields:
            break

    if not merged and req_fields:
        merged = _normalize_schema_fields(req_fields, max_fields=max_fields)

    effective: Dict[str, Any] = {"fields": merged}
    if isinstance(requested_schema.get("dependencies"), dict):
        effective["dependencies"] = requested_schema.get("dependencies")
    if isinstance(requested_schema.get("validations"), list):
        effective["validations"] = requested_schema.get("validations")
    if isinstance(requested_schema.get("required"), list):
        effective["required"] = requested_schema.get("required")

    source = "llm+heuristic" if llm_fields else ("heuristic" if heuristic_fields else "empty")
    return effective, {
        "mode": "auto",
        "source": source,
        "field_count": len(merged),
        "fields": list(merged.keys()),
    }


def _count_table_cells(table_blocks: List[Dict[str, Any]]) -> int:
    count = 0
    for table in table_blocks:
        for row in table.get("rows", []):
            count += len(row.get("cells", []))
    return count


def _tokenize_field_hint(field_name: str) -> Set[str]:
    text = str(field_name or "").strip().lower()
    if not text:
        return set()
    normalized = re.sub(r"[\s_:/\-]+", "", text)
    tokens: Set[str] = set()
    if len(normalized) >= 2:
        tokens.add(normalized)
    for token in re.split(r"[\s_:/\-()]+", text):
        t = token.strip()
        if len(t) >= 2:
            tokens.add(t)
    if re.search(r"[\u4e00-\u9fff]", normalized):
        for idx in range(0, max(0, len(normalized) - 1)):
            frag = normalized[idx : idx + 2]
            if len(frag) == 2:
                tokens.add(frag)
    return {tok for tok in tokens if tok}


def _to_number_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[,\s，￥¥]", "", text)
    cleaned = cleaned.replace("%", "").replace("％", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def _quick_extract_from_tables(table_blocks: List[Dict[str, Any]], schema_fields: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not table_blocks or not schema_fields:
        return out

    for field_name, field_type in schema_fields.items():
        tokens = _tokenize_field_hint(str(field_name))
        if not tokens:
            continue
        wants_number = _coerce_field_type(field_type) == "number"
        best_score = -1
        best_item: Optional[Dict[str, Any]] = None

        for table in table_blocks[:12]:
            for row in table.get("rows", [])[:120]:
                if not isinstance(row, dict):
                    continue
                for cell in row.get("cells", [])[:24]:
                    if not isinstance(cell, dict):
                        continue
                    text = str(cell.get("text") or "").strip()
                    if not text:
                        continue
                    header = str(cell.get("header") or "").strip()
                    merged_header = re.sub(r"\s+", "", f"{header}".lower())
                    merged_text = re.sub(r"\s+", "", text.lower())
                    header_score = sum(2 for tok in tokens if tok in merged_header)
                    text_score = sum(1 for tok in tokens if tok in merged_text)
                    score = header_score + text_score
                    if score <= 0:
                        continue

                    value: Any = text
                    if wants_number:
                        numeric = _to_number_or_none(cell.get("numeric_value"))
                        if numeric is None:
                            numeric = _to_number_or_none(text)
                        if numeric is None:
                            continue
                        value = numeric

                    if score > best_score:
                        best_score = score
                        best_item = {
                            "value": value,
                            "confidence": min(0.95, 0.55 + 0.08 * float(score)),
                            "source_ref_id": str(cell.get("ref_id") or "").strip() or None,
                            "bbox": _normalize_bbox(cell.get("bbox"), page_hint=int(table.get("page", 1) or 1)),
                        }
                    if best_score >= 6:
                        break
                if best_score >= 6:
                    break
            if best_score >= 6:
                break

        if best_item is not None:
            out[str(field_name)] = best_item
    return out


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    text = str(value).strip()
    if not text:
        return False
    return text.lower() not in {"null", "none", "nan", "n/a", "-"}


def _result_quality_snapshot(results: Dict[str, Any], schema_fields: Dict[str, Any]) -> Dict[str, Any]:
    target_total = len(schema_fields)
    filled = 0
    confidence_vals: List[float] = []
    traceable = 0
    for field_name in schema_fields.keys():
        entity = results.get(field_name)
        if not isinstance(entity, dict):
            continue
        if _has_meaningful_value(entity.get("value")):
            filled += 1
        ref_id = str(entity.get("source_ref_id") or "").strip()
        if ref_id:
            traceable += 1
        try:
            conf = float(entity.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf > 0:
            confidence_vals.append(conf)

    all_keys = list(results.keys())
    all_filled = sum(1 for key in all_keys if isinstance(results.get(key), dict) and _has_meaningful_value(results[key].get("value")))
    coverage = (filled / float(target_total)) if target_total > 0 else (1.0 if all_filled > 0 else 0.0)
    trace_ratio = (traceable / float(max(target_total, 1))) if target_total > 0 else 0.0
    avg_conf = (sum(confidence_vals) / len(confidence_vals)) if confidence_vals else 0.0
    return {
        "target_fields": target_total,
        "filled_fields": filled,
        "all_result_fields": len(all_keys),
        "all_filled_fields": all_filled,
        "coverage_ratio": round(coverage, 4),
        "trace_ratio": round(trace_ratio, 4),
        "avg_confidence": round(avg_conf, 4),
    }


def _table_quality_avg(table_blocks: List[Dict[str, Any]]) -> float:
    scores = []
    for table in table_blocks:
        try:
            scores.append(float(table.get("quality", 0.0)))
        except (TypeError, ValueError):
            continue
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def _table_source_counts(table_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for table in table_blocks:
        source = str(table.get("source", "unknown") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _figure_source_counts(figure_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for figure in figure_blocks:
        source = str(figure.get("source", "unknown") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _figure_pages(figure_blocks: List[Dict[str, Any]]) -> List[int]:
    pages = set()
    for figure in figure_blocks:
        try:
            page_no = int(figure.get("page", 0) or 0)
        except (TypeError, ValueError):
            continue
        if page_no > 0:
            pages.add(page_no)
    return sorted(pages)


_REF_RE = re.compile(r'<ref id="([^"]+)">(.*?)</ref>', flags=re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_ref_snippets(markdown: str, max_items: int = 800, max_chars: int = 220) -> Dict[str, str]:
    if not markdown:
        return {}
    out: Dict[str, str] = {}
    for ref_id, raw_text in _REF_RE.findall(markdown):
        key = str(ref_id or "").strip()
        if not key or key in out:
            continue
        text = _TAG_RE.sub(" ", str(raw_text or ""))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        out[key] = text[:max_chars]
        if len(out) >= max_items:
            break
    return out


def _page_from_bbox(bbox: List[float]) -> Optional[int]:
    if not isinstance(bbox, list) or len(bbox) != 5:
        return None
    try:
        page_no = int(round(float(bbox[0])))
    except (TypeError, ValueError):
        return None
    return page_no if page_no >= 1 else None


def _normalize_bbox(bbox: Any, page_hint: Optional[int] = None) -> List[float]:
    if not isinstance(bbox, list):
        return []
    if len(bbox) == 5:
        try:
            return [float(x) for x in bbox[:5]]
        except (TypeError, ValueError):
            return []
    if len(bbox) == 4 and page_hint is not None:
        try:
            return [float(page_hint), float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
        except (TypeError, ValueError):
            return []
    return []


def _artifact_fragment_from_path(path_value: Any) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""
    normalized = raw.replace("\\", "/").strip().lstrip("/")
    root = _artifact_root_dir()

    try:
        candidate = Path(raw).resolve()
    except Exception:
        candidate = None
    if candidate is not None:
        try:
            rel = candidate.relative_to(root)
            return str(rel).replace("\\", "/")
        except Exception:
            pass

    try:
        joined = (root / normalized).resolve()
        rel = joined.relative_to(root)
        return str(rel).replace("\\", "/")
    except Exception:
        return ""


def _artifact_url_from_fragment(fragment: str) -> str:
    cleaned = str(fragment or "").strip().strip("/")
    if not cleaned:
        return ""
    encoded = "/".join(urllib.parse.quote(seg, safe="") for seg in cleaned.split("/") if seg)
    return f"/extract/artifact/{encoded}" if encoded else ""


def _sanitize_file_stem(name: str, fallback: str = "artifact") -> str:
    stem = Path(name or "").stem or fallback
    safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem).strip("_")
    return safe or fallback


def _write_artifact_bytes(*, data: bytes, file_name: str, sub_dir: str, ext: str) -> Tuple[str, str]:
    root = _artifact_root_dir()
    target_dir = (root / sub_dir).resolve()
    try:
        target_dir.relative_to(root)
    except Exception:
        target_dir = root / "preview"
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:16]
    suffix = ext if ext.startswith(".") else f".{ext}"
    fname = f"{_sanitize_file_stem(file_name)}_{digest}{suffix}"
    target = (target_dir / fname).resolve()
    target.write_bytes(data)
    fragment = str(target.relative_to(root)).replace("\\", "/")
    return fragment, _artifact_url_from_fragment(fragment)


def _office_preview_timeout_sec() -> float:
    return max(20.0, float(os.getenv("MODULE2_OFFICE_PREVIEW_TIMEOUT_SEC", "120")))


def _office_convert_enabled() -> bool:
    return (os.getenv("MODULE2_DOC_TO_PDF_ENABLE", "true") or "true").lower() in {"1", "true", "yes"}


def _word_pdf_required() -> bool:
    return (os.getenv("MODULE2_WORD_REQUIRE_PDF_PARSE", "true") or "true").lower() in {"1", "true", "yes"}


def _visual_strict_mode() -> bool:
    return (os.getenv("MODULE2_VISUAL_STRICT", "true") or "true").lower() in {"1", "true", "yes"}


def _office_preview_cleanup_jobs_locked() -> None:
    ttl_sec = max(120.0, float(os.getenv("MODULE2_OFFICE_PREVIEW_JOB_TTL_SEC", "1800")))
    cap = max(20, int(os.getenv("MODULE2_OFFICE_PREVIEW_JOB_CAP", "240")))
    now = time.time()
    expired = [
        job_id
        for job_id, job in office_preview_jobs.items()
        if (now - float(job.updated_at or job.created_at)) > ttl_sec
    ]
    for job_id in expired:
        office_preview_jobs.pop(job_id, None)
    if len(office_preview_jobs) <= cap:
        return
    ordered = sorted(office_preview_jobs.values(), key=lambda x: x.updated_at)
    for item in ordered[: max(0, len(office_preview_jobs) - cap)]:
        office_preview_jobs.pop(item.job_id, None)


def _serialize_office_preview_job(job: OfficePreviewJob) -> Dict[str, Any]:
    return {
        "ok": True,
        "job_id": job.job_id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "file_name": job.file_name,
        "file_hash": job.file_hash,
        "artifact_path": job.artifact_path,
        "artifact_url": job.artifact_url,
        "error": job.error,
        "terminal": job.status in {"completed", "failed"},
    }


def _resolve_trace_artifact_ref(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    direct_url = str(payload.get("artifact_url") or "").strip()
    if direct_url:
        return None, direct_url

    for key in ("artifact_path", "image_path"):
        fragment = _artifact_fragment_from_path(payload.get(key))
        if fragment:
            return fragment, _artifact_url_from_fragment(fragment)
    return None, None


def _is_meaningful_bbox(bbox: List[float]) -> bool:
    if len(bbox) != 5:
        return False
    try:
        _, x, y, w, h = [float(v) for v in bbox[:5]]
    except Exception:
        return False
    if w <= 0 or h <= 0:
        return False
    if x <= 0.0001 and y <= 0.0001 and w >= 0.995 and h >= 0.995:
        return False
    return True


def _crop_pdf_region_png(
    *,
    pdf_bytes: bytes,
    bbox5: List[float],
    dpi: int,
) -> Optional[bytes]:
    if not _is_meaningful_bbox(bbox5):
        return None
    try:
        import fitz  # type: ignore
    except Exception:
        return None
    try:
        page_no = int(round(float(bbox5[0])))
        if page_no < 1:
            return None
        x, y, w, h = [float(v) for v in bbox5[1:5]]
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if page_no > doc.page_count:
                return None
            page = doc.load_page(page_no - 1)
            page_rect = page.rect
            if max(x + w, y + h) <= 1.5:
                x1 = x * page_rect.width
                y1 = y * page_rect.height
                x2 = (x + w) * page_rect.width
                y2 = (y + h) * page_rect.height
            else:
                x1 = x
                y1 = y
                x2 = x + w
                y2 = y + h
            rect = fitz.Rect(x1, y1, x2, y2)
            rect = rect.intersect(page_rect)
            if rect.is_empty or rect.width < 2 or rect.height < 2:
                return None
            zoom = max(1.2, float(dpi) / 72.0)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
            return pix.tobytes("png")
        finally:
            doc.close()
    except Exception:
        return None


def _attach_missing_artifacts_from_pdf(
    *,
    file_name: str,
    file_hash: str,
    pdf_bytes: bytes,
    table_blocks: List[Dict[str, Any]],
    figure_blocks: List[Dict[str, Any]],
) -> None:
    table_dpi = max(120, int(os.getenv("MODULE2_TRACE_TABLE_CROP_DPI", "300")))
    figure_dpi = max(120, int(os.getenv("MODULE2_TRACE_FIGURE_CROP_DPI", "280")))
    max_tables = max(0, int(os.getenv("MODULE2_TRACE_TABLE_ARTIFACT_MAX", "24")))
    max_figures = max(0, int(os.getenv("MODULE2_TRACE_FIGURE_ARTIFACT_MAX", "36")))
    sub_dir = f"trace_rois/{file_hash[:12]}"

    table_done = 0
    for table in table_blocks:
        if table_done >= max_tables:
            break
        if str(table.get("artifact_url") or "").strip() or str(table.get("artifact_path") or "").strip():
            continue
        page_no = int(table.get("page", 0) or 0)
        bbox = _normalize_bbox(table.get("bbox_norm"), page_hint=page_no if page_no > 0 else 1)
        if not _is_meaningful_bbox(bbox):
            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue
                for cell in row.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    bbox = _normalize_bbox(cell.get("bbox"), page_hint=page_no if page_no > 0 else 1)
                    if _is_meaningful_bbox(bbox):
                        break
                if _is_meaningful_bbox(bbox):
                    break
        if not _is_meaningful_bbox(bbox) and page_no > 0:
            bbox = [float(page_no), 0.03, 0.10, 0.94, 0.80]
        if not _is_meaningful_bbox(bbox):
            continue
        png = _crop_pdf_region_png(pdf_bytes=pdf_bytes, bbox5=bbox, dpi=table_dpi)
        if not png:
            continue
        table_id = str(table.get("table_id") or f"table_{table_done+1}")
        frag, url = _write_artifact_bytes(
            data=png,
            file_name=f"{Path(file_name).stem}_{table_id}",
            sub_dir=sub_dir,
            ext=".png",
        )
        table["artifact_path"] = frag
        table["artifact_url"] = url
        table_done += 1

    figure_done = 0
    for figure in figure_blocks:
        if figure_done >= max_figures:
            break
        if str(figure.get("artifact_url") or "").strip() or str(figure.get("artifact_path") or "").strip():
            continue
        page_no = int(figure.get("page", 0) or 0)
        bbox = _normalize_bbox(figure.get("bbox"), page_hint=page_no if page_no > 0 else 1)
        if not _is_meaningful_bbox(bbox):
            bbox = _normalize_bbox(figure.get("bbox_norm"), page_hint=page_no if page_no > 0 else 1)
        if not _is_meaningful_bbox(bbox) and page_no > 0:
            # Last-resort fallback for figure cues without region boxes:
            # keep slightly inset full-page crop so users can still view/copy the figure source page.
            bbox = [float(page_no), 0.03, 0.03, 0.94, 0.94]
        if not _is_meaningful_bbox(bbox):
            continue
        png = _crop_pdf_region_png(pdf_bytes=pdf_bytes, bbox5=bbox, dpi=figure_dpi)
        if not png:
            continue
        figure_id = str(figure.get("figure_id") or f"figure_{figure_done+1}")
        frag, url = _write_artifact_bytes(
            data=png,
            file_name=f"{Path(file_name).stem}_{figure_id}",
            sub_dir=sub_dir,
            ext=".png",
        )
        figure["artifact_path"] = frag
        figure["artifact_url"] = url
        figure_done += 1


def _nonpdf_locator_from_ref(ref_id: Optional[str], file_name: str) -> Dict[str, Any]:
    if not ref_id:
        return {}
    ref = str(ref_id).strip()
    if not ref:
        return {}
    ext = Path(file_name or "").suffix.lower()
    locator: Dict[str, Any] = {}

    if ext == ".xlsx":
        m = re.match(r"^(xlsx(?:_formula)?)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update(
                {
                    "sheet_index": int(m.group(2)),
                    "row_index": int(m.group(3)),
                    "col_index": int(m.group(4)),
                    "ref_scope": "cell",
                }
            )
            return locator
        m = re.match(r"^xlsx_sheet_(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update({"sheet_index": int(m.group(1)), "ref_scope": "sheet"})
            return locator

    if ext == ".docx":
        m = re.match(r"^(docx(?:_relaxed)?)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update(
                {
                    "table_index": int(m.group(2)),
                    "row_index": int(m.group(3)),
                    "col_index": int(m.group(4)),
                    "ref_scope": "cell",
                }
            )
            return locator
        m = re.match(r"^docx(?:_relaxed)?_(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update({"paragraph_index": int(m.group(1)), "ref_scope": "paragraph"})
            return locator

    if ext in {".txt", ".md", ".markdown"}:
        m = re.match(r"^text_(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            chunk_index = int(m.group(1))
            line_start = max(1, (chunk_index - 1) * 12 + 1)
            line_end = line_start + 11
            locator.update(
                {
                    "chunk_index": chunk_index,
                    "line_start": line_start,
                    "line_end": line_end,
                    "ref_scope": "text_chunk",
                }
            )
            return locator
        m = re.match(r"^(md|txt)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update(
                {
                    "table_index": int(m.group(2)),
                    "row_index": int(m.group(3)),
                    "col_index": int(m.group(4)),
                    "ref_scope": "cell",
                }
            )
            return locator
        m = re.match(r"^(md|txt)_fig_(\d+)$", ref, flags=re.IGNORECASE)
        if m:
            locator.update({"figure_index": int(m.group(2)), "ref_scope": "figure_cue"})
            return locator

    return locator


def _table_locator_hint(table: Dict[str, Any], file_name: str) -> Dict[str, Any]:
    ext = Path(file_name or "").suffix.lower()
    if ext == ".xlsx":
        sheet_name = str(table.get("sheet_name") or "").strip()
        out = {
            "sheet_index": int(table.get("sheet_index", table.get("page", 0)) or 0),
            "sheet_name": sheet_name,
        }
        return {k: v for k, v in out.items() if v not in ("", 0, None)}

    if ext == ".docx":
        table_id = str(table.get("table_id") or "")
        m = re.search(r"_t(\d+)", table_id)
        table_index = int(m.group(1)) if m else 0
        return {"table_index": table_index} if table_index > 0 else {}

    return {}


def _figure_locator_hint(figure: Dict[str, Any], file_name: str) -> Dict[str, Any]:
    ext = Path(file_name or "").suffix.lower()
    if ext == ".docx":
        fig_id = str(figure.get("figure_id") or "")
        m = re.search(r"_f(\d+)", fig_id)
        if m:
            return {"figure_index": int(m.group(1))}
    if ext in {".md", ".txt", ".markdown"}:
        fig_id = str(figure.get("figure_id") or "")
        m = re.search(r"_f(\d+)", fig_id)
        if m:
            return {"figure_index": int(m.group(1))}
    return {}


def _build_document_trace_hits(
    *,
    file_name: str,
    file_hash: str,
    results: Dict[str, Any],
    table_blocks: List[Dict[str, Any]],
    figure_blocks: List[Dict[str, Any]],
    markdown: str,
) -> List[Dict[str, Any]]:
    ref_snippets = _extract_ref_snippets(markdown)
    hits: List[Dict[str, Any]] = []

    def _table_preview_payload(table: Dict[str, Any], max_rows: int = 5, max_cols: int = 6) -> Dict[str, Any]:
        headers = [str(x or "").strip() for x in table.get("headers", []) if str(x or "").strip()]
        headers = headers[:max_cols]
        rows_preview: List[List[str]] = []
        for row in table.get("rows", [])[:max_rows]:
            if not isinstance(row, dict):
                continue
            values: List[str] = []
            for cell in row.get("cells", [])[:max_cols]:
                if not isinstance(cell, dict):
                    values.append("")
                    continue
                text = str(cell.get("text") or "").strip()
                values.append(text[:80])
            if any(v for v in values):
                rows_preview.append(values)
        return {
            "headers": headers,
            "rows": rows_preview,
        }

    for field_name, entity in results.items():
        if not isinstance(entity, dict):
            continue
        ref_id = str(entity.get("source_ref_id") or "").strip() or None
        bbox = _normalize_bbox(entity.get("bbox"), page_hint=1)
        page = _page_from_bbox(bbox)
        value = entity.get("value")
        value_text = "null" if value is None else str(value)
        snippet = f"{field_name}: {value_text}"
        if ref_id and ref_id in ref_snippets:
            snippet = f"{snippet} | {ref_snippets[ref_id]}"
        try:
            confidence = float(entity.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        field_locator = {"page": page, "ref_id": ref_id}
        field_locator.update(_nonpdf_locator_from_ref(ref_id, file_name))
        hits.append(
            {
                "file_name": file_name,
                "file_hash": file_hash,
                "object_type": "field",
                "object_id": str(field_name),
                "ref_id": ref_id,
                "page": page,
                "snippet": snippet[:260],
                "confidence": max(0.0, min(1.0, confidence)),
                "locator": field_locator,
                "bbox": bbox,
                "artifact_path": None,
                "artifact_url": None,
                "match_reason": "field_match",
            }
        )

    for table in table_blocks:
        table_id = str(table.get("table_id") or "").strip()
        if not table_id:
            continue
        headers = [str(x).strip() for x in table.get("headers", []) if str(x).strip()]
        row_count = int(table.get("row_count", 0) or 0)
        col_count = int(table.get("col_count", 0) or 0)
        source = str(table.get("source", "") or "")
        page_no = int(table.get("page", 0) or 0)
        artifact_path, artifact_url = _resolve_trace_artifact_ref(table)
        table_ref_id = None
        table_bbox: List[float] = _normalize_bbox(table.get("bbox_norm"), page_hint=page_no if page_no > 0 else 1)
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                table_ref_id = str(cell.get("ref_id") or "").strip() or None
                if not table_bbox:
                    table_bbox = _normalize_bbox(cell.get("bbox"), page_hint=page_no if page_no > 0 else 1)
                if table_ref_id or table_bbox:
                    break
            if table_ref_id or table_bbox:
                break
        page = page_no if page_no > 0 else _page_from_bbox(table_bbox)
        header_text = " | ".join(headers[:4])
        snippet = f"表格 {table_id}（{source}，{row_count}x{col_count}）"
        if header_text:
            snippet = f"{snippet} 标题：{header_text}"
        if table_ref_id and table_ref_id in ref_snippets:
            snippet = f"{snippet} | {ref_snippets[table_ref_id]}"
        try:
            confidence = float(table.get("quality", 0.66) or 0.66)
        except (TypeError, ValueError):
            confidence = 0.66
        table_locator = {
            "page": page,
            "ref_id": table_ref_id,
            "table_preview": _table_preview_payload(table),
            "bbox": table_bbox,
        }
        table_locator.update(_table_locator_hint(table, file_name))
        table_locator.update(_nonpdf_locator_from_ref(table_ref_id, file_name))
        hits.append(
            {
                "file_name": file_name,
                "file_hash": file_hash,
                "object_type": "table",
                "object_id": table_id,
                "ref_id": table_ref_id,
                "page": page,
                "snippet": snippet[:260],
                "confidence": max(0.0, min(1.0, confidence)),
                "locator": table_locator,
                "bbox": table_bbox,
                "artifact_path": artifact_path,
                "artifact_url": artifact_url,
                "match_reason": "table_block",
            }
        )

    for figure in figure_blocks:
        figure_id = str(figure.get("figure_id") or "").strip()
        if not figure_id:
            continue
        page_no = int(figure.get("page", 0) or 0)
        ref_ids = figure.get("ref_ids") if isinstance(figure.get("ref_ids"), list) else []
        figure_ref = str(ref_ids[0]).strip() if ref_ids else ""
        figure_ref = figure_ref or None
        caption = str(figure.get("caption") or "").strip()
        fig_type = str(figure.get("figure_type") or "other")
        source = str(figure.get("source", "") or "")
        quality_raw = figure.get("quality", 0.62)
        try:
            confidence = float(quality_raw if quality_raw is not None else 0.62)
        except (TypeError, ValueError):
            confidence = 0.62
        bbox = _normalize_bbox(figure.get("bbox"), page_hint=page_no if page_no > 0 else 1)
        if not bbox:
            bbox = _normalize_bbox(figure.get("bbox_norm"), page_hint=page_no if page_no > 0 else 1)
        page = page_no if page_no > 0 else _page_from_bbox(bbox)
        snippet = caption or f"图像 {figure_id}"
        if figure_ref and figure_ref in ref_snippets:
            snippet = f"{snippet} | {ref_snippets[figure_ref]}"
        artifact_path, artifact_url = _resolve_trace_artifact_ref(figure)
        key_points_raw = figure.get("key_points")
        if not isinstance(key_points_raw, list):
            key_points_raw = figure.get("insights") if isinstance(figure.get("insights"), list) else []
        key_points = [str(x) for x in key_points_raw if str(x).strip()][:6]
        content_modes = [
            str(x).strip().lower()
            for x in (figure.get("content_modes") if isinstance(figure.get("content_modes"), list) else [])
            if str(x).strip()
        ][:4]
        dataframe_raw = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
        dataframe_headers = [
            str(x).strip()
            for x in (dataframe_raw.get("headers") if isinstance(dataframe_raw.get("headers"), list) else [])
            if str(x).strip()
        ][:10]
        dataframe_rows: List[List[str]] = []
        rows_raw = dataframe_raw.get("rows") if isinstance(dataframe_raw.get("rows"), list) else []
        for row in rows_raw[:8]:
            if not isinstance(row, list):
                continue
            vals = [str(v).strip() for v in row[:10]]
            if any(vals):
                dataframe_rows.append(vals)
        topology_raw = figure.get("topology") if isinstance(figure.get("topology"), dict) else {}
        topology_nodes = topology_raw.get("nodes") if isinstance(topology_raw.get("nodes"), list) else []
        topology_edges = topology_raw.get("edges") if isinstance(topology_raw.get("edges"), list) else []
        text_blocks = [
            str(x).strip()
            for x in (figure.get("text_blocks") if isinstance(figure.get("text_blocks"), list) else [])
            if str(x).strip()
        ][:8]
        figure_locator = {
            "page": page,
            "ref_id": figure_ref,
            "figure_type": fig_type,
            "caption": caption,
            "key_points": key_points,
            "content_modes": content_modes,
            "dataframe": {
                "headers": dataframe_headers,
                "rows": dataframe_rows,
            },
            "topology": {
                "nodes": topology_nodes[:20],
                "edges": topology_edges[:30],
            },
            "text_blocks": text_blocks,
        }
        figure_locator.update(_figure_locator_hint(figure, file_name))
        figure_locator.update(_nonpdf_locator_from_ref(figure_ref, file_name))
        hits.append(
            {
                "file_name": file_name,
                "file_hash": file_hash,
                "object_type": "figure",
                "object_id": figure_id,
                "ref_id": figure_ref,
                "page": page,
                "snippet": f"{fig_type}:{snippet} ({source})"[:260],
                "confidence": max(0.0, min(1.0, confidence)),
                "locator": figure_locator,
                "bbox": bbox,
                "artifact_path": artifact_path,
                "artifact_url": artifact_url,
                "match_reason": "figure_block",
            }
        )

    dedup: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for item in hits:
        key = (
            str(item.get("object_type", "")),
            str(item.get("object_id", "")),
            str(item.get("ref_id") or ""),
            str(item.get("snippet", ""))[:120],
        )
        prev = dedup.get(key)
        if prev is None:
            dedup[key] = item
            continue
        try:
            prev_conf = float(prev.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            prev_conf = 0.0
        try:
            cur_conf = float(item.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            cur_conf = 0.0
        if cur_conf >= prev_conf:
            dedup[key] = item

    out = list(dedup.values())
    out.sort(key=lambda x: (float(x.get("confidence", 0.0) or 0.0), str(x.get("object_type", ""))), reverse=True)
    trace_cap = max(80, int(os.getenv("MODULE2_TRACE_HITS_MAX", "420")))
    return out[:trace_cap]


def _trace_stats(trace_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    count_by_type: Dict[str, int] = {}
    page_set = set()
    for hit in trace_hits:
        typ = str(hit.get("object_type", "unknown") or "unknown")
        count_by_type[typ] = count_by_type.get(typ, 0) + 1
        try:
            page_no = int(hit.get("page", 0) or 0)
        except (TypeError, ValueError):
            page_no = 0
        if page_no > 0:
            page_set.add(page_no)
    return {
        "trace_hit_count": len(trace_hits),
        "trace_object_counts": count_by_type,
        "trace_pages": sorted(page_set),
    }


def _build_polymorphic_links(
    *,
    results: Dict[str, Any],
    trace_hits: List[Dict[str, Any]],
    max_links: int = 80,
) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    if not isinstance(results, dict) or not trace_hits:
        return links

    table_hits = [h for h in trace_hits if str(h.get("object_type", "")).lower() == "table"]
    figure_hits = [h for h in trace_hits if str(h.get("object_type", "")).lower() == "figure"]

    for field_name, entity in results.items():
        if not isinstance(entity, dict):
            continue
        ref_id = str(entity.get("source_ref_id") or "").strip()
        bbox = _normalize_bbox(entity.get("bbox"), page_hint=1)
        page = _page_from_bbox(bbox)
        related_targets: List[Dict[str, Any]] = []

        for hit in table_hits:
            hit_ref = str(hit.get("ref_id") or "").strip()
            hit_page = int(hit.get("page", 0) or 0)
            ref_match = bool(ref_id and hit_ref and ref_id == hit_ref)
            page_match = bool(page and hit_page and page == hit_page)
            if not ref_match and not page_match:
                continue
            related_targets.append(
                {
                    "type": "table",
                    "id": str(hit.get("object_id") or ""),
                    "page": hit_page or None,
                    "confidence": float(hit.get("confidence", 0.0) or 0.0),
                    "match": "ref_id" if ref_match else "page",
                }
            )

        for hit in figure_hits:
            hit_page = int(hit.get("page", 0) or 0)
            if not (page and hit_page and page == hit_page):
                continue
            related_targets.append(
                {
                    "type": "figure",
                    "id": str(hit.get("object_id") or ""),
                    "page": hit_page or None,
                    "confidence": float(hit.get("confidence", 0.0) or 0.0),
                    "match": "page",
                }
            )

        if not related_targets:
            continue
        related_targets.sort(key=lambda x: float(x.get("confidence", 0.0) or 0.0), reverse=True)
        links.append(
            {
                "field": str(field_name),
                "ref_id": ref_id or None,
                "page": page,
                "targets": related_targets[:8],
            }
        )
        if len(links) >= max_links:
            break
    return links


def _decode_text_with_fallback(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="ignore")


def _preflight_nonpdf_profile(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    name = (file_name or "").lower()
    _, ext = os.path.splitext(name)
    ext = ext or ""
    size_mb = round(len(file_bytes) / (1024.0 * 1024.0), 3)

    signals: Dict[str, Any] = {
        "ext": ext,
        "size_mb": size_mb,
        "docx_media_count": 0,
        "docx_chart_xml_count": 0,
        "md_image_links": 0,
        "md_table_rows": 0,
        "txt_table_lines": 0,
        "figure_keyword_hits": 0,
    }

    profile = "text_heavy"
    figure_pattern = re.compile(r"(图表|图\d+|表\d+|figure|chart|diagram|柱状图|折线图|饼图)", re.IGNORECASE)

    if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
        profile = "chart_heavy"
        return {"profile": profile, "signals": signals}

    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = zf.namelist()
            media_count = sum(1 for n in names if n.startswith("word/media/"))
            chart_xml_count = sum(1 for n in names if n.startswith("word/charts/") and n.endswith(".xml"))
            signals["docx_media_count"] = media_count
            signals["docx_chart_xml_count"] = chart_xml_count
            if chart_xml_count >= 1 or media_count >= 3:
                profile = "chart_heavy"
            elif media_count >= 1:
                profile = "mixed"
        except Exception:
            profile = "mixed" if size_mb >= 4 else "text_heavy"
        return {"profile": profile, "signals": signals}

    if ext == ".xlsx":
        profile = "table_heavy"
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = zf.namelist()
            sheet_count = sum(
                1
                for n in names
                if n.startswith("xl/worksheets/") and n.endswith(".xml")
            )
            chart_count = sum(
                1
                for n in names
                if n.startswith("xl/charts/") and n.endswith(".xml")
            )
            signals["xlsx_sheet_count"] = sheet_count
            signals["xlsx_chart_count"] = chart_count
            if chart_count >= 2 and sheet_count <= 2:
                profile = "chart_heavy"
            elif sheet_count <= 2 and size_mb <= 0.9:
                profile = "mixed"
        except Exception:
            profile = "table_heavy" if size_mb >= 0.6 else "mixed"
        return {"profile": profile, "signals": signals}

    if ext in {".md", ".markdown", ".txt"}:
        text = _decode_text_with_fallback(file_bytes)
        lines = [line.rstrip("\n") for line in text.splitlines()]
        kw_hits = len(figure_pattern.findall(text[:120000]))
        signals["figure_keyword_hits"] = kw_hits

        if ext in {".md", ".markdown"}:
            md_images = len(re.findall(r"!\[[^\]]*]\(([^)]+)\)", text))
            md_table_rows = sum(1 for line in lines if line.count("|") >= 2 and len(line.strip()) >= 6)
            signals["md_image_links"] = md_images
            signals["md_table_rows"] = md_table_rows
            if md_images >= 2 or (md_images >= 1 and md_table_rows >= 3) or kw_hits >= 6:
                profile = "chart_heavy"
            elif md_images >= 1 or md_table_rows >= 2 or kw_hits >= 2:
                profile = "mixed"
            return {"profile": profile, "signals": signals}

        txt_table_lines = sum(
            1
            for line in lines
            if ("\t" in line and len([p for p in line.split("\t") if p.strip()]) >= 3)
            or (line.count(",") >= 2 and len([p for p in line.split(",") if p.strip()]) >= 3)
            or len(re.findall(r"\s{2,}", line)) >= 2
        )
        signals["txt_table_lines"] = txt_table_lines
        if txt_table_lines >= 8 and kw_hits >= 2:
            profile = "chart_heavy"
        elif txt_table_lines >= 4 or kw_hits >= 2:
            profile = "mixed"
        return {"profile": profile, "signals": signals}

    if size_mb >= 8:
        profile = "mixed"
    return {"profile": profile, "signals": signals}


def _resolve_nonpdf_budgets(profile: str) -> Dict[str, float]:
    parse_default = max(5.0, float(os.getenv("MODULE2_PARSE_TIMEOUT_SEC", "120")))
    extract_default = max(8.0, float(os.getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "120")))
    total_cap = max(30.0, float(os.getenv("MODULE2_NONPDF_TOTAL_BUDGET_SEC", "90")))

    profile_key = (profile or "text_heavy").strip().lower()
    if profile_key not in {"text_heavy", "mixed", "chart_heavy", "table_heavy"}:
        profile_key = "mixed"
    if profile_key == "table_heavy":
        total_cap = max(total_cap, float(os.getenv("MODULE2_NONPDF_TOTAL_BUDGET_TABLE_SEC", "88")))

    parse_cap_map = {
        "text_heavy": max(10.0, float(os.getenv("MODULE2_NONPDF_PARSE_TEXT_SEC", "24"))),
        "mixed": max(12.0, float(os.getenv("MODULE2_NONPDF_PARSE_MIXED_SEC", "34"))),
        "chart_heavy": max(15.0, float(os.getenv("MODULE2_NONPDF_PARSE_CHART_SEC", "42"))),
        "table_heavy": max(14.0, float(os.getenv("MODULE2_NONPDF_PARSE_TABLE_SEC", "24"))),
    }
    extract_cap_map = {
        "text_heavy": max(12.0, float(os.getenv("MODULE2_NONPDF_EXTRACT_TEXT_SEC", "34"))),
        "mixed": max(15.0, float(os.getenv("MODULE2_NONPDF_EXTRACT_MIXED_SEC", "44"))),
        "chart_heavy": max(18.0, float(os.getenv("MODULE2_NONPDF_EXTRACT_CHART_SEC", "52"))),
        "table_heavy": max(24.0, float(os.getenv("MODULE2_NONPDF_EXTRACT_TABLE_SEC", "64"))),
    }

    parse_timeout = min(parse_default, parse_cap_map[profile_key])
    extract_timeout = min(extract_default, extract_cap_map[profile_key])
    total = parse_timeout + extract_timeout
    if total > total_cap:
        ratio = total_cap / max(total, 1e-6)
        parse_timeout = max(5.0, parse_timeout * ratio)
        extract_timeout = max(8.0, extract_timeout * ratio)

    return {
        "profile": profile_key,
        "parse_timeout_sec": round(parse_timeout, 3),
        "extract_timeout_sec": round(extract_timeout, 3),
        "total_budget_sec": round(total_cap, 3),
    }


def _normalize_soft_warnings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        msg = str(item or "").strip()
        if msg and msg not in out:
            out.append(msg)
    return out


def _artifact_root_dir() -> Path:
    root = Path(os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "backend/module2/.cache")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_artifact_path(path_fragment: str) -> Path:
    root = _artifact_root_dir()
    fragment = str(path_fragment or "").strip().lstrip("/\\")
    target = (root / fragment).resolve()
    try:
        target.relative_to(root)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    return target


def _head_response_for_file(file_path: Path) -> Response:
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(file_path.stat().st_size),
            "Content-Type": media_type,
        },
    )


def _bridge_public_base_url() -> str:
    raw = (os.getenv("MODULE2_DIFY_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    return raw


def _bridge_token_required() -> bool:
    return (os.getenv("MODULE2_DIFY_BRIDGE_REQUIRE_TOKEN", "true") or "true").lower() in {"1", "true", "yes"}


def _bridge_shared_token() -> str:
    return (os.getenv("MODULE2_DIFY_SHARED_TOKEN", "") or "").strip()


def _bridge_check_token(request: Request) -> None:
    if not _bridge_token_required():
        return
    expected = _bridge_shared_token()
    if not expected:
        # Safe default: in required mode but token unset, reject all bridge calls.
        raise HTTPException(status_code=503, detail="Bridge token is not configured")
    got = (request.headers.get("X-Module2-Token", "") or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _bridge_allow_http_remote() -> bool:
    return (os.getenv("MODULE2_DIFY_ALLOW_HTTP", "false") or "false").lower() in {"1", "true", "yes"}


def _bridge_remote_timeout_sec() -> float:
    return max(3.0, float(os.getenv("MODULE2_DIFY_REMOTE_TIMEOUT_SEC", "20")))


def _bridge_max_file_mb() -> int:
    return max(1, int(os.getenv("MODULE2_MAX_FILE_MB", "25")))


def _bridge_remote_allowed_hosts() -> List[str]:
    raw = (os.getenv("MODULE2_DIFY_REMOTE_ALLOWED_HOSTS", "") or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for item in raw.split(","):
        host = item.strip().lower()
        if host and host not in out:
            out.append(host)
    return out


def _bridge_block_private_hosts() -> bool:
    return (os.getenv("MODULE2_DIFY_BLOCK_PRIVATE_HOSTS", "true") or "true").lower() in {"1", "true", "yes"}


def _bridge_host_matches_allowlist(host: str, allowlist: List[str]) -> bool:
    if not allowlist:
        return True
    host = host.strip().lower().rstrip(".")
    for item in allowlist:
        normalized = item.strip().lower().rstrip(".")
        if not normalized:
            continue
        if normalized.startswith("*."):
            suffix = normalized[2:]
            if host.endswith(f".{suffix}") or host == suffix:
                return True
            continue
        if host == normalized:
            return True
    return False


def _bridge_resolve_host_ips(host: str) -> List[ipaddress._BaseAddress]:
    ips: List[ipaddress._BaseAddress] = []
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return ips
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_raw = str(sockaddr[0] or "").strip()
        if not ip_raw:
            continue
        try:
            ip_obj = ipaddress.ip_address(ip_raw)
        except ValueError:
            continue
        ips.append(ip_obj)
    return ips


def _bridge_ip_blocked(ip_obj: ipaddress._BaseAddress) -> bool:
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _bridge_make_request_id(payload: BridgeJobCreateRequest) -> str:
    canonical = {
        "schema": payload.schema,
        "max_retries": payload.max_retries,
        "files": [
            {
                "name": item.pick_name(idx),
                "url": item.pick_url(),
                "base64_len": len(item.pick_base64()),
            }
            for idx, item in enumerate(payload.files, start=1)
        ],
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bridge_download_remote_file(url: str, timeout_sec: float, max_file_bytes: int) -> bytes:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = str(parsed.hostname or "").strip().lower()
    if scheme not in {"https", "http"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file URL scheme: {scheme}")
    if scheme == "http" and not _bridge_allow_http_remote():
        raise HTTPException(status_code=400, detail="HTTP file URL is not allowed")
    if not host:
        raise HTTPException(status_code=400, detail="File URL host is missing")

    allowlist = _bridge_remote_allowed_hosts()
    if not _bridge_host_matches_allowlist(host, allowlist):
        raise HTTPException(status_code=400, detail=f"File URL host is not allowed: {host}")

    if _bridge_block_private_hosts():
        resolved_ips = _bridge_resolve_host_ips(host)
        if not resolved_ips:
            raise HTTPException(status_code=400, detail=f"File URL host cannot be resolved: {host}")
        for ip_obj in resolved_ips:
            if _bridge_ip_blocked(ip_obj):
                raise HTTPException(status_code=400, detail=f"File URL host points to private address: {ip_obj}")

    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "module2-bridge/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status >= 400:
                raise HTTPException(status_code=400, detail=f"File URL returned status {status}")
            content = resp.read(max_file_bytes + 1)
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"File URL returned status {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=400, detail=f"File URL fetch failed: {exc.reason}") from exc
    if len(content) > max_file_bytes:
        raise HTTPException(status_code=413, detail=f"Remote file too large. Max size is {_bridge_max_file_mb()}MB")
    if not content:
        raise HTTPException(status_code=400, detail="Remote file is empty")
    return content


def _bridge_decode_base64_file(raw: str, max_file_bytes: int) -> bytes:
    value = (raw or "").strip()
    if value.startswith("data:"):
        comma = value.find(",")
        value = value[comma + 1 :] if comma >= 0 else ""
    try:
        decoded = base64.b64decode(value, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 file payload") from exc
    if len(decoded) > max_file_bytes:
        raise HTTPException(status_code=413, detail=f"Inline file too large. Max size is {_bridge_max_file_mb()}MB")
    if not decoded:
        raise HTTPException(status_code=400, detail="Inline file is empty")
    return decoded


def _bridge_load_input_files(payload: BridgeJobCreateRequest) -> List[Tuple[str, bytes]]:
    timeout_sec = _bridge_remote_timeout_sec()
    max_file_bytes = _bridge_max_file_mb() * 1024 * 1024
    loaded: List[Tuple[str, bytes]] = []
    for idx, item in enumerate(payload.files, start=1):
        name = item.pick_name(idx)
        url = item.pick_url()
        if url:
            content = _bridge_download_remote_file(url=url, timeout_sec=timeout_sec, max_file_bytes=max_file_bytes)
            if "." not in name:
                guessed_name = os.path.basename(urllib.parse.urlparse(url).path)
                if guessed_name:
                    name = guessed_name
        else:
            content = _bridge_decode_base64_file(item.pick_base64(), max_file_bytes=max_file_bytes)
        loaded.append((name, content))
    return loaded


def _bridge_job_progress(job: BridgeJobState) -> Dict[str, Any]:
    done = int(job.completed_files + job.failed_files)
    total = int(job.total_files)
    ratio = (done / float(total)) if total > 0 else 0.0
    return {
        "total_files": total,
        "completed_files": int(job.completed_files),
        "failed_files": int(job.failed_files),
        "progress_ratio": round(ratio, 4),
    }


def _serialize_bridge_job(job: BridgeJobState, include_documents: bool) -> Dict[str, Any]:
    base = _bridge_public_base_url()
    payload: Dict[str, Any] = {
        "ok": True,
        "job_id": job.job_id,
        "request_id": job.request_id,
        "status": job.status,
        "terminal": job.terminal(),
        "file_names": list(job.file_names),
        "progress": _bridge_job_progress(job),
        "errors": list(job.errors),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    if base:
        payload["dify_status_url"] = f"{base}/dify/module2/jobs/status"
        payload["dify_trace_url"] = f"{base}/dify/module2/trace/locate"
    if include_documents:
        payload["documents"] = [doc.model_dump(mode="json") for doc in job.documents]
    return payload


def _bridge_cleanup_jobs_locked() -> None:
    """Best-effort in-memory retention to avoid unbounded growth."""
    ttl_sec = max(300, int(os.getenv("MODULE2_DIFY_JOB_TTL_SEC", "21600")))
    max_jobs = max(16, int(os.getenv("MODULE2_DIFY_MAX_JOBS", "512")))
    now_ts = time.time()
    stale_ids = [
        job_id
        for job_id, job in bridge_jobs.items()
        if job.terminal() and (now_ts - float(job.updated_at)) > ttl_sec
    ]
    for job_id in stale_ids:
        req_id = bridge_jobs[job_id].request_id
        bridge_jobs.pop(job_id, None)
        if bridge_request_index.get(req_id) == job_id:
            bridge_request_index.pop(req_id, None)
    if len(bridge_jobs) <= max_jobs:
        return
    ordered = sorted(bridge_jobs.values(), key=lambda j: float(j.updated_at))
    overflow = max(0, len(ordered) - max_jobs)
    for job in ordered[:overflow]:
        req_id = job.request_id
        bridge_jobs.pop(job.job_id, None)
        if bridge_request_index.get(req_id) == job.job_id:
            bridge_request_index.pop(req_id, None)


def _filter_trace_hits(
    hits: List[Dict[str, Any]],
    *,
    field_name: str = "",
    file_name: str = "",
    file_hash: str = "",
    ref_id: str = "",
    object_type: str = "",
    keyword: str = "",
) -> List[Dict[str, Any]]:
    field_name = (field_name or "").strip().lower()
    file_name = (file_name or "").strip().lower()
    file_hash = (file_hash or "").strip().lower()
    ref_id = (ref_id or "").strip()
    object_type = (object_type or "").strip().lower()
    keyword = (keyword or "").strip().lower()

    out: List[Dict[str, Any]] = []
    for hit in hits:
        if file_name and str(hit.get("file_name", "")).lower() != file_name:
            continue
        if file_hash and str(hit.get("file_hash", "")).lower() != file_hash:
            continue
        if object_type and str(hit.get("object_type", "")).lower() != object_type:
            continue
        if ref_id and str(hit.get("ref_id", "") or "") != ref_id:
            continue
        if field_name:
            object_id = str(hit.get("object_id", "")).lower()
            snippet = str(hit.get("snippet", "")).lower()
            if object_id != field_name and f"{field_name}:" not in snippet:
                continue
        if keyword:
            snippet = str(hit.get("snippet", "")).lower()
            if keyword not in snippet:
                continue
        out.append(hit)
    out.sort(key=lambda x: float(x.get("confidence", 0.0) or 0.0), reverse=True)
    return out


def _trace_hits_from_job(job: BridgeJobState, req: BridgeTraceLocateRequest) -> List[Dict[str, Any]]:
    all_hits: List[Dict[str, Any]] = []
    for doc in job.documents:
        prebuilt = getattr(doc, "trace_hits", []) or []
        if prebuilt:
            for item in prebuilt:
                if isinstance(item, dict):
                    all_hits.append(dict(item))
                elif hasattr(item, "model_dump"):
                    all_hits.append(item.model_dump(mode="json"))
            continue
        for field_name, entity in doc.result.root.items():
            ref_val = str(entity.source_ref_id or "").strip()
            ref_id = ref_val or None
            bbox = list(entity.bbox or []) if isinstance(entity.bbox, list) else []
            page = int(round(float(bbox[0]))) if len(bbox) == 5 else None
            all_hits.append(
                {
                    "file_name": doc.file_name,
                    "file_hash": doc.file_hash,
                    "object_type": "field",
                    "object_id": field_name,
                    "ref_id": ref_id,
                    "page": page,
                    "snippet": f"{field_name}: {entity.value if entity.value is not None else 'null'}",
                    "confidence": float(entity.confidence or 0.0),
                    "locator": {"page": page, "ref_id": ref_id},
                    "bbox": bbox if len(bbox) == 5 else [],
                    "artifact_path": None,
                    "artifact_url": None,
                    "match_reason": "field_match",
                }
            )

    return _filter_trace_hits(
        all_hits,
        field_name=req.field_name or "",
        file_name=req.file_name or "",
        file_hash=req.file_hash or "",
        ref_id=req.ref_id or "",
        object_type=req.object_type or "",
        keyword=req.keyword or "",
    )


def _summarize_document_payload(req: SummarizeRequest) -> str:
    lines: List[str] = []
    lines.append(f"文档：{req.file_name}")
    if req.errors:
        lines.append(f"存在错误：{'; '.join(req.errors[:3])}")
    if req.soft_warnings:
        lines.append(f"提示：{'; '.join(req.soft_warnings[:3])}")

    result_items = []
    for key, value in req.result.items():
        if not isinstance(value, dict):
            continue
        field_val = value.get("value")
        conf = value.get("confidence")
        if field_val is None:
            continue
        try:
            conf_pct = f"{int(round(float(conf or 0.0) * 100))}%"
        except Exception:
            conf_pct = "--"
        result_items.append(f"{key}={field_val}（置信度 {conf_pct}）")
        if len(result_items) >= 8:
            break
    if result_items:
        lines.append("已抽取字段：" + "；".join(result_items))
    else:
        lines.append("未抽取到有效字段。")

    diag = req.diagnostics or {}
    table_count = int(diag.get("table_count", 0) or 0)
    figure_count = int(diag.get("figure_count", 0) or 0)
    parse_ms = int(diag.get("parse_ms", 0) or 0)
    extract_ms = int(diag.get("extract_ms", 0) or 0)
    total_ms = int(diag.get("total_ms", parse_ms + extract_ms) or 0)
    lines.append(
        f"结构识别：表格 {table_count} 张，图像/图表 {figure_count} 张；耗时约 {total_ms}ms（解析 {parse_ms}ms，抽取 {extract_ms}ms）。"
    )

    summary = " ".join(lines).strip()
    max_chars = int(req.max_chars or 400)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


_FIELD_LABELS = {
    "contract_amount": "合同金额",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "tax_rate": "税率",
    "region": "地区",
    "invoice_number": "发票号码",
    "invoice_date": "开票日期",
    "buyer_name": "购买方名称",
    "seller_name": "销售方名称",
    "total_amount": "合计金额",
}
_ASSISTANT_PERSIST_HINTS = ("入库", "落库", "保存", "存储", "写入数据库", "写库")
_ASSISTANT_ALL_HINTS = ("全部", "所有", "全量", "完整", "所有字段", "全部字段")


def _assistant_field_label(field_name: str) -> str:
    return _FIELD_LABELS.get(field_name, field_name)


def _assistant_should_persist(user_instruction: str, explicit: bool) -> bool:
    if explicit:
        return True
    text = str(user_instruction or "").strip().lower()
    return any(hint in text for hint in _ASSISTANT_PERSIST_HINTS)


def _assistant_match_fields(
    doc: DocumentExtractionResponse,
    user_instruction: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    result_root = doc.result.root if isinstance(doc.result.root, dict) else {}
    instruction = str(user_instruction or "").strip().lower()
    wants_all = any(token in instruction for token in _ASSISTANT_ALL_HINTS)

    matched: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    for field_name, entity in result_root.items():
        if entity.value is None:
            continue
        label = _assistant_field_label(field_name)
        page = _page_from_bbox(entity.bbox if isinstance(entity.bbox, list) else [])
        item = {
            "field_name": field_name,
            "label": label,
            "value": entity.value,
            "confidence": float(entity.confidence or 0.0),
            "source_ref_id": entity.source_ref_id,
            "page": page,
            "bbox": list(entity.bbox or []) if isinstance(entity.bbox, list) else [],
        }
        fallback.append(item)

        field_hit = field_name.lower() in instruction
        label_hit = label.lower() in instruction
        if wants_all or field_hit or label_hit:
            matched.append(item)

    if not matched:
        matched = sorted(fallback, key=lambda x: float(x.get("confidence", 0.0)), reverse=True)[: max(1, min(top_k, 6))]
    return matched[:top_k]


def _assistant_collect_trace_hits(
    doc: DocumentExtractionResponse,
    matched_fields: List[Dict[str, Any]],
    user_instruction: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    source_hits_raw = doc.trace_hits if isinstance(doc.trace_hits, list) else []
    source_hits: List[Dict[str, Any]] = []
    for item in source_hits_raw:
        if isinstance(item, dict):
            source_hits.append(dict(item))
        elif hasattr(item, "model_dump"):
            source_hits.append(item.model_dump(mode="json"))

    if not source_hits:
        source_hits = _build_document_trace_hits(
            file_name=doc.file_name,
            file_hash=doc.file_hash,
            results=doc.result.root if isinstance(doc.result.root, dict) else {},
            table_blocks=[],
            figure_blocks=[],
            markdown="",
        )

    out: List[Dict[str, Any]] = []
    instruction = str(user_instruction or "").strip().lower()
    wanted_keys = {str(item.get("field_name", "")).lower() for item in matched_fields if item.get("field_name")}
    for hit in source_hits:
        object_id = str(hit.get("object_id", "")).strip().lower()
        snippet = str(hit.get("snippet", "")).strip().lower()
        if wanted_keys and object_id in wanted_keys:
            out.append(hit)
            continue
        if instruction and instruction in snippet:
            out.append(hit)
    if not out:
        out = source_hits
    out.sort(key=lambda x: float(x.get("confidence", 0.0) or 0.0), reverse=True)
    return out[:top_k]


def _assistant_build_answer(
    summary_text: str,
    user_instruction: str,
    matched_fields: List[Dict[str, Any]],
    matched_trace_hits: List[Dict[str, Any]],
    persisted: bool,
    persisted_rows: int,
) -> str:
    parts: List[str] = []
    cleaned_summary = str(summary_text or "").strip()
    if cleaned_summary:
        parts.append(f"已基于摘要上下文完成指令解析：{cleaned_summary[:220]}")
    parts.append(f"你的需求：{str(user_instruction or '').strip()}")

    if matched_fields:
        preview_items = []
        for item in matched_fields[:5]:
            label = str(item.get("label", item.get("field_name", "字段")))
            value = item.get("value")
            preview_items.append(f"{label}={value}")
        parts.append(f"已匹配 {len(matched_fields)} 个字段：{'；'.join(preview_items)}。")
    else:
        parts.append("未匹配到可用字段，请调整提取描述后重试。")

    parts.append(f"已关联溯源片段 {len(matched_trace_hits)} 条。")
    if persisted:
        parts.append(f"已完成数据库写入，记录数 {persisted_rows}。")
    else:
        parts.append("本次未执行数据库写入。")
    return " ".join(parts)


def _clear_artifact_cache_dir() -> int:
    root = _artifact_root_dir()
    removed = 0
    for child in root.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
            elif child.is_file():
                child.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    return removed


@app.on_event("startup")
async def startup_event() -> None:
    await storage.connect()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await storage.close()
    process_pool.shutdown(wait=False, cancel_futures=True)


def _is_recoverable_timeout_error(message: str) -> bool:
    text = str(message or "").lower()
    return ("timeout" in text) and (
        "table_extract" in text or "field_extract" in text or "llm" in text or "gemini" in text
    )


async def _convert_word_to_pdf_with_timeout(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float,
) -> Tuple[bytes, Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(
            None,
            lambda: convert_word_bytes_to_pdf(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=timeout_sec,
            ),
        ),
        timeout=timeout_sec,
    )


async def _run_office_preview_job(job_id: str, file_name: str, file_bytes: bytes) -> None:
    async with office_preview_lock:
        job = office_preview_jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = time.time()

    try:
        timeout_sec = _office_preview_timeout_sec()
        pdf_bytes, convert_meta = await _convert_word_to_pdf_with_timeout(
            file_name=file_name,
            file_bytes=file_bytes,
            timeout_sec=timeout_sec,
        )
        frag, url = _write_artifact_bytes(
            data=pdf_bytes,
            file_name=file_name,
            sub_dir="preview/office_pdf",
            ext=".pdf",
        )
        async with office_preview_lock:
            job = office_preview_jobs.get(job_id)
            if not job:
                return
            job.status = "completed"
            job.updated_at = time.time()
            job.artifact_path = frag
            job.artifact_url = url
            if convert_meta:
                job.error = ""
    except Exception as exc:
        async with office_preview_lock:
            job = office_preview_jobs.get(job_id)
            if not job:
                return
            job.status = "failed"
            job.updated_at = time.time()
            job.error = f"{type(exc).__name__}: {exc}"


async def _process_single_doc_bytes(
    file_name: str,
    file_bytes: bytes,
    schema: Dict[str, Any],
    schema_hash: str,
    max_retries: int,
) -> DocumentExtractionResponse:
    t0 = time.perf_counter()
    router = StreamRouter(storage)
    decision = await router.triage(file_name, file_bytes, schema_hash)

    if decision.cached_payload is not None:
        cached_result = decision.cached_payload.get("result", {})
        cached_errors_raw = decision.cached_payload.get("errors", [])
        cached_errors = [str(x) for x in cached_errors_raw] if isinstance(cached_errors_raw, list) else []
        cached_soft_warnings = _normalize_soft_warnings(decision.cached_payload.get("soft_warnings", []))
        cached_trace_hits_raw = decision.cached_payload.get("trace_hits", [])
        cached_trace_hits = cached_trace_hits_raw if isinstance(cached_trace_hits_raw, list) else []
        cached_trace_stats_raw = decision.cached_payload.get("trace_stats", {})
        cached_trace_stats = cached_trace_stats_raw if isinstance(cached_trace_stats_raw, dict) else {}
        cached_track = str(decision.cached_payload.get("track", decision.track))
        cached_diag_raw = decision.cached_payload.get("diagnostics", decision.cached_payload.get("metrics", {}))
        cached_diag = cached_diag_raw if isinstance(cached_diag_raw, dict) else {}
        return DocumentExtractionResponse(
            file_name=file_name,
            file_hash=decision.file_hash,
            track=cached_track,
            cached=True,
            result=ExtractionResult(cached_result),
            errors=cached_errors,
            soft_warnings=cached_soft_warnings,
            trace_hits=cached_trace_hits,
            trace_stats=cached_trace_stats,
            diagnostics=cached_diag,
        )

    loop = asyncio.get_running_loop()
    parse_timeout_sec = max(5.0, float(os.getenv("MODULE2_PARSE_TIMEOUT_SEC", "150")))
    extract_timeout_sec = max(8.0, float(os.getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "120")))
    nonpdf_preflight: Optional[Dict[str, Any]] = None
    nonpdf_budget: Optional[Dict[str, float]] = None
    nonpdf_total_budget_sec: Optional[float] = None
    nonpdf_guard_sec = max(1.0, float(os.getenv("MODULE2_NONPDF_BUDGET_GUARD_SEC", "2.0")))
    word_parse_extract_budget_sec: Optional[float] = None
    word_convert_budget_sec: Optional[float] = None
    word_pdf_required = _word_pdf_required()
    if not file_name.lower().endswith(".pdf"):
        nonpdf_preflight = _preflight_nonpdf_profile(file_name=file_name, file_bytes=file_bytes)
        nonpdf_budget = _resolve_nonpdf_budgets(str(nonpdf_preflight.get("profile", "mixed")))
        parse_timeout_sec = float(nonpdf_budget["parse_timeout_sec"])
        extract_timeout_sec = float(nonpdf_budget["extract_timeout_sec"])
        nonpdf_total_budget_sec = float(nonpdf_budget.get("total_budget_sec", 90.0))
        if is_word_file(file_name):
            word_parse_extract_budget_sec = max(
                24.0,
                float(os.getenv("MODULE2_WORD_PARSE_EXTRACT_BUDGET_SEC", "70")),
            )
            word_convert_budget_sec = max(12.0, float(os.getenv("MODULE2_WORD_CONVERT_BUDGET_SEC", "24")))
            if nonpdf_total_budget_sec is not None:
                max_convert_budget = max(12.0, nonpdf_total_budget_sec - 20.0)
                word_convert_budget_sec = min(word_convert_budget_sec, max_convert_budget)
                parse_extract_cap = max(
                    18.0,
                    nonpdf_total_budget_sec - word_convert_budget_sec - nonpdf_guard_sec,
                )
                word_parse_extract_budget_sec = min(word_parse_extract_budget_sec, parse_extract_cap)
            parse_extract_total = parse_timeout_sec + extract_timeout_sec
            if parse_extract_total > word_parse_extract_budget_sec:
                ratio = word_parse_extract_budget_sec / max(parse_extract_total, 1e-6)
                parse_timeout_sec = max(5.0, parse_timeout_sec * ratio)
                extract_timeout_sec = max(8.0, extract_timeout_sec * ratio)
                parse_extract_total = parse_timeout_sec + extract_timeout_sec
            # Word=>PDF parsing is usually the bottleneck; reserve more parse budget to reduce hard timeouts.
            if parse_extract_total > 12.0:
                target_parse_share = max(
                    0.45,
                    min(0.9, float(os.getenv("MODULE2_WORD_PARSE_SHARE", "0.62"))),
                )
                min_word_parse_timeout = max(
                    18.0,
                    float(os.getenv("MODULE2_WORD_PARSE_TIMEOUT_MIN_SEC", "32")),
                )
                target_parse_timeout = max(
                    parse_timeout_sec,
                    parse_extract_total * target_parse_share,
                    min_word_parse_timeout,
                )
                parse_timeout_sec = min(target_parse_timeout, parse_extract_total - 8.0)
                extract_timeout_sec = max(8.0, parse_extract_total - parse_timeout_sec)

    parse_t0 = time.perf_counter()
    parse_track = decision.track
    parse_warning: Optional[str] = None
    figure_blocks: List[Dict[str, Any]] = []
    parse_stats: Dict[str, Any] = {}
    parse_input_name = file_name
    parse_input_bytes = file_bytes
    conversion_diag: Dict[str, Any] = {}

    if is_word_file(file_name) and not _office_convert_enabled() and word_pdf_required:
        raise HTTPException(
            status_code=503,
            detail=(
                "Word 转 PDF 功能已禁用，当前配置要求 DOC/DOCX 必须先转为 PDF 后再解析。"
            ),
        )

    if is_word_file(file_name) and _office_convert_enabled():
        convert_timeout_default = max(20.0, float(os.getenv("MODULE2_DOC_TO_PDF_TIMEOUT_SEC", "60")))
        convert_timeout_sec = convert_timeout_default
        if word_convert_budget_sec is not None:
            convert_timeout_sec = min(convert_timeout_sec, max(12.0, float(word_convert_budget_sec)))
        if nonpdf_total_budget_sec is not None:
            elapsed_before_convert = max(0.0, time.perf_counter() - t0)
            remaining_for_convert = (
                nonpdf_total_budget_sec
                - elapsed_before_convert
                - (parse_timeout_sec + extract_timeout_sec + nonpdf_guard_sec)
            )
            if remaining_for_convert > 0:
                convert_timeout_sec = min(convert_timeout_sec, max(12.0, remaining_for_convert))
            else:
                raise HTTPException(
                    status_code=504,
                    detail=f"Non-PDF budget exhausted before Word->PDF conversion for {file_name}",
                )
        convert_timeout_sec = max(12.0, convert_timeout_sec)
        convert_t0 = time.perf_counter()
        try:
            pdf_bytes, convert_meta = await _convert_word_to_pdf_with_timeout(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=convert_timeout_sec,
            )
            parse_input_name = f"{Path(file_name).stem}.pdf"
            parse_input_bytes = pdf_bytes
            parse_track = "VisualTrack"
            frag, url = _write_artifact_bytes(
                data=pdf_bytes,
                file_name=file_name,
                sub_dir="preview/office_pdf",
                ext=".pdf",
            )
            conversion_diag = {
                "office_pdf_converted": True,
                "office_pdf_converter": str(convert_meta.get("converter", "")),
                "office_pdf_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
                "office_pdf_timeout_sec": round(convert_timeout_sec, 3),
                "office_pdf_preview_path": frag,
                "office_pdf_preview_url": url,
                "office_pdf_total_ms": int((time.perf_counter() - convert_t0) * 1000),
            }
        except Exception as exc:
            conversion_diag = {
                "office_pdf_converted": False,
                "office_pdf_error": f"{type(exc).__name__}: {exc}",
                "office_pdf_timeout_sec": round(convert_timeout_sec, 3),
                "office_pdf_total_ms": int((time.perf_counter() - convert_t0) * 1000),
            }
            suffix = Path(file_name).suffix.lower()
            allow_native_fallback = (
                suffix == ".docx"
                and (os.getenv("MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK", "true").lower() in {"1", "true", "yes"})
            )
            if (word_pdf_required and not allow_native_fallback) or suffix == ".doc":
                raise HTTPException(
                    status_code=422,
                    detail=f"Word 转 PDF 失败，无法处理 {file_name}: {type(exc).__name__}: {exc}",
                ) from exc
            parse_track = "FastTrack"
            parse_input_name = file_name
            parse_input_bytes = file_bytes
            parse_warning = f"doc_to_pdf_fallback_native:{type(exc).__name__}"

    if parse_input_name.lower().endswith(".pdf"):
        parse_track = "VisualTrack"

    if nonpdf_total_budget_sec is not None:
        elapsed_before_parse = max(0.0, time.perf_counter() - t0)
        remaining_budget = nonpdf_total_budget_sec - elapsed_before_parse
        parse_extract_total = parse_timeout_sec + extract_timeout_sec
        if remaining_budget > 0 and (parse_extract_total + nonpdf_guard_sec) > remaining_budget:
            allowed = max(13.0, remaining_budget - nonpdf_guard_sec)
            ratio = allowed / max(parse_extract_total, 1e-6)
            parse_timeout_sec = max(5.0, parse_timeout_sec * ratio)
            extract_timeout_sec = max(8.0, extract_timeout_sec * ratio)
            if parse_warning:
                parse_warning = f"{parse_warning}|nonpdf_budget_tight"
            else:
                parse_warning = "nonpdf_budget_tight"

    def _unpack_parse_output(
        parsed: Any,
    ) -> tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        if isinstance(parsed, tuple):
            if len(parsed) == 5:
                markdown, refs, tables, figures, extra_stats = parsed
                stats = extra_stats if isinstance(extra_stats, dict) else {}
                return markdown, refs, tables, figures if isinstance(figures, list) else [], stats
            if len(parsed) == 4:
                markdown, refs, tables, figures = parsed
                return markdown, refs, tables, figures if isinstance(figures, list) else [], {}
            if len(parsed) == 3:
                markdown, refs, tables = parsed
                return markdown, refs, tables, [], {}
        raise ValueError("Unexpected parse output shape")

    try:
        parsed_output = await asyncio.wait_for(
            loop.run_in_executor(process_pool, parse_document_in_subprocess, parse_input_bytes, parse_input_name, parse_track),
            timeout=parse_timeout_sec,
        )
        marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
    except TimeoutError as exc:
        is_word_pdf_parse = is_word_file(file_name) and parse_input_name.lower().endswith(".pdf")
        if is_word_pdf_parse:
            fallback_timeout = max(12.0, min(60.0, parse_timeout_sec))
            if nonpdf_total_budget_sec is not None:
                elapsed_now = max(0.0, time.perf_counter() - t0)
                remaining_budget = nonpdf_total_budget_sec - elapsed_now - max(6.0, nonpdf_guard_sec)
                if remaining_budget <= 6.0:
                    raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from exc
                fallback_timeout = min(fallback_timeout, max(6.0, remaining_budget))
            try:
                parsed_output = await asyncio.wait_for(
                    loop.run_in_executor(
                        process_pool,
                        parse_document_in_subprocess,
                        file_bytes,
                        file_name,
                        "FastTrack",
                    ),
                    timeout=fallback_timeout,
                )
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
                parse_track = "VisualTrack->WordNativeFallback"
                fallback_hint = "word_pdf_parse_timeout_fallback_native"
                parse_warning = f"{parse_warning}|{fallback_hint}" if parse_warning else fallback_hint
            except TimeoutError as fallback_exc:
                raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from fallback_exc
            except Exception as fallback_exc:
                fallback_message = str(fallback_exc)
                if "Unsupported file type" in fallback_message:
                    raise HTTPException(status_code=400, detail=fallback_message) from fallback_exc
                raise HTTPException(
                    status_code=500,
                    detail=f"Native parsing failed for {file_name}: {fallback_exc}",
                ) from fallback_exc
        else:
            raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from exc
    except Exception as exc:
        message = str(exc)
        lower_message = message.lower()
        visual_strict = _visual_strict_mode()
        visual_backend_missing = (
            ("VisualTrack OCR backend is unavailable" in message)
            or ("rapidocr_onnxruntime" in lower_message)
            or ("pymupdf" in lower_message)
        )
        visual_pipeline_unusable = (
            "visual-first pipeline returned no usable result" in lower_message
            or ("mineru" in lower_message and ("failed" in lower_message or "not found" in lower_message))
        )
        if parse_track == "VisualTrack" and parse_input_name.lower().endswith(".pdf"):
            if visual_backend_missing and visual_strict:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "VisualTrack OCR backend unavailable and strict mode is enabled. "
                        "Please install pymupdf/rapidocr-onnxruntime or disable MODULE2_VISUAL_STRICT."
                    ),
                ) from exc

            fallback_warning: str | None = None
            if visual_backend_missing and not visual_strict:
                fallback_warning = "VisualTrack OCR backend unavailable, auto-fallback to native FastTrack parsing."
            elif visual_pipeline_unusable and not visual_strict:
                fallback_warning = "VisualTrack/MinerU returned no usable layout, auto-fallback to native FastTrack parsing."

            if fallback_warning:
                parse_track = "VisualTrack->FastTrackFallback"
                parse_warning = f"{parse_warning}|{fallback_warning}" if parse_warning else fallback_warning
                try:
                    parsed_output = await asyncio.wait_for(
                        loop.run_in_executor(
                            process_pool,
                            parse_document_in_subprocess,
                            parse_input_bytes,
                            parse_input_name,
                            "FastTrack",
                        ),
                        timeout=parse_timeout_sec,
                    )
                    marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
                except TimeoutError as fallback_exc:
                    raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from fallback_exc
                except Exception as fallback_exc:
                    fallback_message = str(fallback_exc)
                    if "Unsupported file type" in fallback_message:
                        raise HTTPException(status_code=400, detail=fallback_message) from fallback_exc
                    raise HTTPException(
                        status_code=500,
                        detail=f"Native parsing failed for {file_name}: {fallback_exc}",
                    ) from fallback_exc
            elif visual_strict and visual_pipeline_unusable:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "VisualTrack/MinerU parsing failed in strict mode. "
                        "Please verify MinerU runtime and Gemini configuration before retrying."
                    ),
                ) from exc
            elif "Unsupported file type" in message:
                raise HTTPException(status_code=400, detail=message) from exc
            elif "backend is unavailable" in lower_message or "please install" in lower_message:
                raise HTTPException(status_code=503, detail=message) from exc
            else:
                raise HTTPException(status_code=500, detail=f"Native parsing failed for {file_name}: {exc}") from exc
        else:
            if "Unsupported file type" in message:
                raise HTTPException(status_code=400, detail=message) from exc
            if "backend is unavailable" in lower_message or "please install" in lower_message:
                raise HTTPException(status_code=503, detail=message) from exc
            raise HTTPException(status_code=500, detail=f"Native parsing failed for {file_name}: {exc}") from exc
    parse_ms = int((time.perf_counter() - parse_t0) * 1000)

    auto_schema_llm_max_mb = max(0.2, float(os.getenv("MODULE2_AUTO_SCHEMA_LLM_MAX_FILE_MB", "1.2")))
    allow_schema_llm = (len(file_bytes) / (1024.0 * 1024.0) <= auto_schema_llm_max_mb) and len(table_blocks) <= 12
    effective_schema, schema_meta = await _resolve_effective_schema(
        requested_schema=schema,
        file_name=file_name,
        markdown=marked_markdown,
        table_blocks=table_blocks,
        profile_hint=str((nonpdf_preflight or {}).get("profile", "")),
        allow_llm=allow_schema_llm,
    )
    effective_schema_fields = (
        effective_schema.get("fields")
        if isinstance(effective_schema.get("fields"), dict)
        else {}
    )

    init_state: AgentState = {
        "markdown": marked_markdown,
        "bbox_map": bbox_map,
        "table_blocks": table_blocks,
        "table_summary": "",
        "field_hints": {},
        "schema": effective_schema,
        "results": {},
        "errors": [],
        "soft_warnings": [],
        "retries": 0,
        "max_retries": max_retries,
    }

    extract_t0 = time.perf_counter()
    used_quick_fallback = False
    try:
        final_state = await asyncio.wait_for(graph.run(init_state), timeout=extract_timeout_sec)
    except TimeoutError as exc:
        fallback_results = _quick_extract_from_tables(
            table_blocks=table_blocks,
            schema_fields=effective_schema_fields,
        )
        if str(schema_meta.get("mode", "")) == "auto":
            used_quick_fallback = True
            warning = (
                f"quick_table_fallback:Extraction timed out for {file_name}"
                if fallback_results
                else f"auto_timeout_no_fields:{file_name}"
            )
            final_state = {
                "results": fallback_results,
                "errors": [],
                "soft_warnings": [warning],
            }
        else:
            raise HTTPException(status_code=504, detail=f"Extraction timed out for {file_name}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction graph failed for {file_name}: {exc}") from exc
    extract_ms = int((time.perf_counter() - extract_t0) * 1000)
    total_ms = int((time.perf_counter() - t0) * 1000)

    final_results = final_state.get("results", {})
    if not isinstance(final_results, dict):
        final_results = {}
    final_errors = list(final_state.get("errors", []))
    soft_warnings = _normalize_soft_warnings(final_state.get("soft_warnings", []))
    if parse_warning:
        soft_warnings.append(parse_warning)
    if nonpdf_total_budget_sec is not None and total_ms > int(nonpdf_total_budget_sec * 1000):
        over_ms = total_ms - int(nonpdf_total_budget_sec * 1000)
        soft_warnings.append(f"nonpdf_budget_exceeded:{over_ms}")
    if used_quick_fallback:
        min_conf = max(0.35, min(0.95, float(os.getenv("MODULE2_QUICK_FALLBACK_MIN_CONF", "0.58"))))
        filtered_results: Dict[str, Dict[str, Any]] = {}
        dropped = 0
        for field_name, entity in final_results.items():
            if not isinstance(entity, dict):
                dropped += 1
                continue
            try:
                confidence = float(entity.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < min_conf or not _has_meaningful_value(entity.get("value")):
                dropped += 1
                continue
            filtered_results[str(field_name)] = entity
        if dropped > 0:
            soft_warnings.append(f"quick_table_fallback_filtered:{dropped}")
        final_results = filtered_results
        hint = f"quick_table_fallback_used:{file_name}"
        if hint not in soft_warnings:
            soft_warnings.append(hint)
    if final_results and final_errors:
        retained_errors: List[str] = []
        for err in final_errors:
            if _is_recoverable_timeout_error(err):
                downgraded = f"downgraded:{err}"
                if downgraded not in soft_warnings:
                    soft_warnings.append(downgraded)
            else:
                retained_errors.append(err)
        final_errors = retained_errors

    quality_snapshot = _result_quality_snapshot(final_results, effective_schema_fields)
    coverage_ratio = float(quality_snapshot.get("coverage_ratio", 0.0) or 0.0)
    avg_conf = float(quality_snapshot.get("avg_confidence", 0.0) or 0.0)
    min_coverage = max(0.15, min(1.0, float(os.getenv("MODULE2_MIN_COVERAGE_RATIO", "0.35"))))
    min_confidence = max(0.2, min(1.0, float(os.getenv("MODULE2_MIN_AVG_CONFIDENCE", "0.55"))))
    degraded_reasons: List[str] = []
    if quality_snapshot.get("target_fields", 0) and coverage_ratio < min_coverage:
        degraded_reasons.append(f"low_coverage:{coverage_ratio:.3f}")
    if quality_snapshot.get("filled_fields", 0) > 0 and avg_conf < min_confidence:
        degraded_reasons.append(f"low_confidence:{avg_conf:.3f}")
    if used_quick_fallback:
        degraded_reasons.append("quick_fallback")
    if degraded_reasons:
        soft_warnings.append(f"quality_gate_degraded:{'|'.join(degraded_reasons)}")
    else:
        soft_warnings.append("quality_gate_ok")
    soft_warnings = _normalize_soft_warnings(soft_warnings)

    if parse_input_name.lower().endswith(".pdf"):
        try:
            _attach_missing_artifacts_from_pdf(
                file_name=file_name,
                file_hash=decision.file_hash,
                pdf_bytes=parse_input_bytes,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
            )
        except Exception as exc:
            soft_warnings.append(f"trace_artifact_crop_failed:{type(exc).__name__}")
            soft_warnings = _normalize_soft_warnings(soft_warnings)

    trace_hits = _build_document_trace_hits(
        file_name=file_name,
        file_hash=decision.file_hash,
        results=final_results,
        table_blocks=table_blocks,
        figure_blocks=figure_blocks,
        markdown=marked_markdown,
    )
    trace_stats = _trace_stats(trace_hits)
    polymorphic_links = _build_polymorphic_links(results=final_results, trace_hits=trace_hits)

    diagnostics = {
        "parse_ms": parse_ms,
        "extract_ms": extract_ms,
        "total_ms": total_ms,
        "parse_input_name": parse_input_name,
        "parse_input_bytes": len(parse_input_bytes),
        "markdown_len": len(marked_markdown),
        "refs": len(bbox_map),
        "table_count": len(table_blocks),
        "table_cells": _count_table_cells(table_blocks),
        "table_quality_avg": _table_quality_avg(table_blocks),
        "table_sources": _table_source_counts(table_blocks),
        "figure_count": len(figure_blocks),
        "figure_pages": _figure_pages(figure_blocks),
        "figure_sources": _figure_source_counts(figure_blocks),
        "soft_warning_count": len(soft_warnings),
        "parse_timeout_sec": parse_timeout_sec,
        "extract_timeout_sec": extract_timeout_sec,
        "nonpdf_total_budget_sec": nonpdf_total_budget_sec,
        "word_pdf_required": bool(word_pdf_required) if is_word_file(file_name) else False,
        "word_parse_extract_budget_sec": word_parse_extract_budget_sec,
        "word_convert_budget_sec": word_convert_budget_sec,
        "schema_mode": schema_meta.get("mode", "manual"),
        "schema_source": schema_meta.get("source", "request"),
        "schema_field_count": int(schema_meta.get("field_count", 0) or 0),
        "schema_fields": list(schema_meta.get("fields", []))[:24],
        "schema_llm_planner_enabled": bool(allow_schema_llm),
        "quick_fallback_used": bool(used_quick_fallback),
        "quality_status": "degraded" if degraded_reasons else "ok",
        "quality_reasons": degraded_reasons,
        "quality_snapshot": quality_snapshot,
        "polymorphic_link_count": len(polymorphic_links),
        "polymorphic_links": polymorphic_links[:40],
    }
    if conversion_diag:
        diagnostics.update(conversion_diag)
    diagnostics.update(trace_stats)
    if parse_stats:
        diagnostics["parse_stats"] = parse_stats
        for key in (
            "plain_ext",
            "docx_chart_xml_seen",
            "docx_chart_xml_parsed",
            "docx_media_seen",
            "docx_media_used",
            "docx_media_parsed",
            "docx_media_parse_errors",
            "docx_media_skipped_duplicate",
        ):
            if key in parse_stats:
                diagnostics[key] = parse_stats.get(key)
    if nonpdf_preflight is not None:
        diagnostics["nonpdf_profile"] = nonpdf_preflight.get("profile", "mixed")
        diagnostics["nonpdf_signals"] = nonpdf_preflight.get("signals", {})
    if nonpdf_budget is not None:
        diagnostics["nonpdf_budget"] = nonpdf_budget
        diagnostics["nonpdf_elapsed_ms"] = total_ms

    response = DocumentExtractionResponse(
        file_name=file_name,
        file_hash=decision.file_hash,
        track=parse_track,
        cached=False,
        result=ExtractionResult(final_results),
        errors=final_errors,
        soft_warnings=soft_warnings,
        trace_hits=trace_hits,
        trace_stats=trace_stats,
        diagnostics=diagnostics,
    )

    await storage.save_extraction_result(
        decision.cache_key,
        {
            "file_name": file_name,
            "file_hash": decision.file_hash,
            "schema_hash": schema_hash,
            "cache_key": decision.cache_key,
            "track": parse_track,
            "cached": False,
            "result": response.result.model_dump(mode="json"),
            "errors": response.errors,
            "soft_warnings": response.soft_warnings,
            "trace_hits": [
                (item.model_dump(mode="json") if hasattr(item, "model_dump") else item)
                for item in response.trace_hits
            ],
            "trace_stats": response.trace_stats,
            "diagnostics": diagnostics,
            "metrics": diagnostics,
            "tables": table_blocks,
            "figures": figure_blocks,
        },
    )

    return response


async def process_single_doc(
    file: UploadFile,
    schema: Dict[str, Any],
    schema_hash: str,
    max_retries: int,
) -> DocumentExtractionResponse:
    file_name = file.filename or "unknown"
    max_file_mb = max(1, int(os.getenv("MODULE2_MAX_FILE_MB", "25")))
    max_file_bytes = max_file_mb * 1024 * 1024
    file_bytes = await file.read(max_file_bytes + 1)
    if len(file_bytes) > max_file_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_name}. Max size is {max_file_mb}MB.",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail=f"Empty file: {file_name}")
    return await _process_single_doc_bytes(file_name, file_bytes, schema, schema_hash, max_retries)


def _error_doc_response(file_name: str, exc: Exception) -> DocumentExtractionResponse:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            message = detail
        else:
            message = json.dumps(detail, ensure_ascii=False)
    else:
        message = str(exc) or "Unexpected extraction failure"
    return DocumentExtractionResponse(
        file_name=file_name,
        file_hash="",
        track="Error",
        cached=False,
        result=ExtractionResult({}),
        errors=[message],
        diagnostics={},
    )


@app.post("/extract/batch", response_model=BatchExtractionResponse)
async def extract_batch(
    files: List[UploadFile] = File(...),
    schema: str = Form(...),
) -> BatchExtractionResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    if len(files) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    try:
        schema_obj = json.loads(schema)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {exc}") from exc
    if not isinstance(schema_obj, dict):
        raise HTTPException(status_code=400, detail="Schema must be a JSON object")

    schema_digest = _schema_hash(schema_obj)
    max_retries = max(0, min(int(os.getenv("MODULE2_MAX_RETRIES", "2")), 6))
    concurrency = max(1, min(int(os.getenv("MODULE2_BATCH_CONCURRENCY", "2")), len(files)))
    sem = asyncio.Semaphore(concurrency)

    async def _run(file: UploadFile) -> DocumentExtractionResponse:
        async with sem:
            return await process_single_doc(file, schema_obj, schema_digest, max_retries)

    tasks = [_run(file) for file in files]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    results: List[DocumentExtractionResponse] = []
    for file, item in zip(files, gathered):
        if isinstance(item, Exception):
            results.append(_error_doc_response(file.filename or "unknown", item))
        else:
            results.append(item)
    return BatchExtractionResponse(documents=results)


@app.post("/extract/preview/office/start")
async def extract_preview_office_start(file: UploadFile = File(...)) -> Dict[str, Any]:
    file_name = file.filename or "unknown.docx"
    if not is_word_file(file_name):
        raise HTTPException(status_code=400, detail="Only .doc/.docx preview conversion is supported")
    if not _office_convert_enabled():
        raise HTTPException(status_code=503, detail="DOC/DOCX preview conversion is disabled")

    max_file_mb = max(1, int(os.getenv("MODULE2_MAX_FILE_MB", "25")))
    max_file_bytes = max_file_mb * 1024 * 1024
    file_bytes = await file.read(max_file_bytes + 1)
    if len(file_bytes) > max_file_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max {max_file_mb}MB")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    async with office_preview_lock:
        _office_preview_cleanup_jobs_locked()
        for existing in office_preview_jobs.values():
            if existing.file_hash == file_hash and existing.status == "completed" and existing.artifact_url:
                return _serialize_office_preview_job(existing)
        job_id = f"preview_{uuid.uuid4().hex[:16]}"
        now = time.time()
        job = OfficePreviewJob(
            job_id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
            file_name=file_name,
            file_hash=file_hash,
            artifact_path=None,
            artifact_url=None,
            error="",
        )
        office_preview_jobs[job_id] = job

    asyncio.create_task(_run_office_preview_job(job_id, file_name, file_bytes))
    async with office_preview_lock:
        created = office_preview_jobs.get(job_id)
        if not created:
            raise HTTPException(status_code=500, detail="preview job lost")
        return _serialize_office_preview_job(created)


@app.get("/extract/preview/office/status/{job_id}")
async def extract_preview_office_status(job_id: str) -> Dict[str, Any]:
    async with office_preview_lock:
        _office_preview_cleanup_jobs_locked()
        job = office_preview_jobs.get(str(job_id).strip())
        if not job:
            raise HTTPException(status_code=404, detail="Preview job not found")
        return _serialize_office_preview_job(job)


async def _run_bridge_job(
    job_id: str,
    schema: Dict[str, Any],
    schema_hash: str,
    max_retries: int,
    loaded_files: List[Tuple[str, bytes]],
) -> None:
    async with bridge_lock:
        job = bridge_jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = time.time()

    for file_name, file_bytes in loaded_files:
        try:
            doc = await _process_single_doc_bytes(
                file_name=file_name,
                file_bytes=file_bytes,
                schema=schema,
                schema_hash=schema_hash,
                max_retries=max_retries,
            )
            async with bridge_lock:
                job = bridge_jobs.get(job_id)
                if not job:
                    return
                job.documents.append(doc)
                if doc.errors:
                    job.failed_files += 1
                else:
                    job.completed_files += 1
                job.updated_at = time.time()
        except Exception as exc:
            async with bridge_lock:
                job = bridge_jobs.get(job_id)
                if not job:
                    return
                job.failed_files += 1
                job.errors.append(f"{file_name}: {type(exc).__name__}: {exc}")
                job.updated_at = time.time()

    async with bridge_lock:
        job = bridge_jobs.get(job_id)
        if not job:
            return
        done = job.completed_files + job.failed_files
        if done < job.total_files:
            job.status = "running"
        elif job.completed_files == 0:
            job.status = "failed"
        else:
            job.status = "completed"
        job.updated_at = time.time()


@app.post("/dify/module2/jobs/create")
async def dify_module2_jobs_create(request: Request, payload: BridgeJobCreateRequest) -> Dict[str, Any]:
    _bridge_check_token(request)

    if not isinstance(payload.schema, dict):
        raise HTTPException(status_code=400, detail="schema must be a JSON object")
    request_id = (payload.request_id or "").strip() or _bridge_make_request_id(payload)

    async with bridge_lock:
        _bridge_cleanup_jobs_locked()
        existing_job_id = bridge_request_index.get(request_id)
        if existing_job_id and existing_job_id in bridge_jobs:
            existing = bridge_jobs[existing_job_id]
            return _serialize_bridge_job(existing, include_documents=False)

    loaded_files = _bridge_load_input_files(payload)
    if not loaded_files:
        raise HTTPException(status_code=400, detail="No valid files provided")

    job_id = f"job_{uuid.uuid4().hex[:16]}"
    now = time.time()
    file_names = [name for name, _ in loaded_files]
    job_state = BridgeJobState(
        job_id=job_id,
        request_id=request_id,
        status="queued",
        created_at=now,
        updated_at=now,
        total_files=len(loaded_files),
        completed_files=0,
        failed_files=0,
        file_names=file_names,
        documents=[],
        errors=[],
    )
    async with bridge_lock:
        bridge_jobs[job_id] = job_state
        bridge_request_index[request_id] = job_id

    schema_hash = _schema_hash(payload.schema)
    asyncio.create_task(
        _run_bridge_job(
            job_id=job_id,
            schema=payload.schema,
            schema_hash=schema_hash,
            max_retries=payload.max_retries,
            loaded_files=loaded_files,
        )
    )

    return _serialize_bridge_job(job_state, include_documents=False)


@app.post("/dify/module2/jobs/status")
async def dify_module2_jobs_status(request: Request, payload: BridgeJobStatusRequest) -> Dict[str, Any]:
    _bridge_check_token(request)
    async with bridge_lock:
        _bridge_cleanup_jobs_locked()
        job = bridge_jobs.get(payload.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _serialize_bridge_job(job, include_documents=payload.include_documents)


@app.post("/dify/module2/trace/locate")
async def dify_module2_trace_locate(request: Request, payload: BridgeTraceLocateRequest) -> Dict[str, Any]:
    _bridge_check_token(request)
    async with bridge_lock:
        _bridge_cleanup_jobs_locked()
        job = bridge_jobs.get(payload.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_snapshot = BridgeJobState(
            job_id=job.job_id,
            request_id=job.request_id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            total_files=job.total_files,
            completed_files=job.completed_files,
            failed_files=job.failed_files,
            file_names=list(job.file_names),
            documents=list(job.documents),
            errors=list(job.errors),
        )

    all_hits = _trace_hits_from_job(job_snapshot, payload)
    top_k = int(payload.top_k)
    hits = all_hits[:top_k]
    return {
        "ok": True,
        "job_id": job_snapshot.job_id,
        "job_status": job_snapshot.status,
        "terminal": job_snapshot.terminal(),
        "hit_count": len(all_hits),
        "truncated": len(all_hits) > len(hits),
        "hits": hits,
    }


@app.post("/extract/summarize", response_model=SummarizeResponse)
async def extract_summarize(payload: SummarizeRequest) -> SummarizeResponse:
    return SummarizeResponse(summary=_summarize_document_payload(payload))


@app.post("/extract/trace/locate", response_model=TraceLocateResponse)
async def extract_trace_locate(payload: TraceLocateRequest) -> TraceLocateResponse:
    doc = payload.document
    source_hits_raw = doc.trace_hits if isinstance(doc.trace_hits, list) else []
    source_hits: List[Dict[str, Any]] = []
    for item in source_hits_raw:
        if isinstance(item, dict):
            source_hits.append(dict(item))
        elif hasattr(item, "model_dump"):
            source_hits.append(item.model_dump(mode="json"))
    if not source_hits:
        result_payload = doc.result.model_dump(mode="json")
        if (
            isinstance(result_payload, dict)
            and "root" in result_payload
            and isinstance(result_payload.get("root"), dict)
            and len(result_payload) == 1
        ):
            result_payload = result_payload["root"]
        source_hits = _build_document_trace_hits(
            file_name=doc.file_name,
            file_hash=doc.file_hash,
            results=result_payload if isinstance(result_payload, dict) else {},
            table_blocks=[],
            figure_blocks=[],
            markdown="",
        )

    all_hits = _filter_trace_hits(
        source_hits,
        field_name=payload.field_name or "",
        file_name=payload.file_name or "",
        file_hash=payload.file_hash or "",
        ref_id=payload.ref_id or "",
        object_type=payload.object_type or "",
        keyword=payload.keyword or "",
    )
    top_k = int(payload.top_k)
    hits = all_hits[:top_k]
    return TraceLocateResponse(
        hit_count=len(all_hits),
        truncated=len(all_hits) > len(hits),
        hits=hits,
    )


@app.post("/extract/assistant/query", response_model=AssistantQueryResponse)
async def extract_assistant_query(payload: AssistantQueryRequest) -> AssistantQueryResponse:
    doc = payload.document
    instruction = str(payload.user_instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="user_instruction is required")

    summary_text = str(payload.summary or "").strip()
    top_k = int(payload.top_k)
    matched_fields = _assistant_match_fields(doc=doc, user_instruction=instruction, top_k=top_k)
    matched_trace_hits = _assistant_collect_trace_hits(
        doc=doc,
        matched_fields=matched_fields,
        user_instruction=instruction,
        top_k=max(6, top_k),
    )

    persist = _assistant_should_persist(user_instruction=instruction, explicit=bool(payload.persist))
    persisted_rows = 0
    warnings: List[str] = []
    if persist:
        try:
            persisted_rows = await storage.save_assistant_interaction(
                {
                    "file_hash": doc.file_hash,
                    "file_name": doc.file_name,
                    "user_instruction": instruction,
                    "summary_text": summary_text,
                    "matched": matched_fields,
                }
            )
            if not matched_fields:
                warnings.append("已写入交互记录，但当前未匹配到可入库字段。")
        except Exception as exc:
            warnings.append(f"入库失败：{type(exc).__name__}: {exc}")

    answer = _assistant_build_answer(
        summary_text=summary_text,
        user_instruction=instruction,
        matched_fields=matched_fields,
        matched_trace_hits=matched_trace_hits,
        persisted=bool(persisted_rows > 0),
        persisted_rows=persisted_rows,
    )
    return AssistantQueryResponse(
        ok=True,
        answer=answer,
        summary_used=summary_text,
        matched_fields=matched_fields,
        matched_trace_hits=matched_trace_hits,
        persisted=bool(persisted_rows > 0),
        persisted_rows=persisted_rows,
        warnings=warnings,
    )


@app.post("/extract/cache/clear", response_model=CacheClearResponse)
async def extract_cache_clear() -> CacheClearResponse:
    cache_counts = await storage.clear_runtime_cache()
    removed_artifacts = _clear_artifact_cache_dir()
    return CacheClearResponse(
        ok=True,
        message="模块二缓存已清理",
        cache_counts=cache_counts,
        removed_artifacts=removed_artifacts,
    )


@app.api_route("/extract/layout-preview/{artifact_name}", methods=["GET", "HEAD"])
async def extract_layout_preview(artifact_name: str, request: Request) -> Response:
    target = _safe_artifact_path(f"layout/{artifact_name}")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Layout preview not found: {artifact_name}")
    if request.method.upper() == "HEAD":
        return _head_response_for_file(target)
    media_type = mimetypes.guess_type(str(target))[0] or "application/pdf"
    return FileResponse(path=target, media_type=media_type, filename=target.name)


@app.api_route("/extract/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
async def extract_artifact(artifact_path: str, request: Request) -> Response:
    target = _safe_artifact_path(artifact_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_path}")
    if request.method.upper() == "HEAD":
        return _head_response_for_file(target)
    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(path=target, media_type=media_type, filename=target.name)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {
        "status": "ok",
        "bridge_jobs_in_memory": str(len(bridge_jobs)),
        "bridge_request_index_size": str(len(bridge_request_index)),
        "office_preview_jobs_in_memory": str(len(office_preview_jobs)),
        "bridge_token_required": str(_bridge_token_required()).lower(),
        "bridge_remote_allow_http": str(_bridge_allow_http_remote()).lower(),
        "storage_db_connected": str(storage.diagnostics().get("db_connected", False)).lower(),
        "storage_degraded_memory_mode": str(storage.diagnostics().get("degraded_memory_mode", False)).lower(),
    }

