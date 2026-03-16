from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import io
import json
import logging
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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

MODULE2_ROOT = Path(__file__).resolve().parents[1]

# Always load Module 2's own env file so uvicorn startup from repo root
# does not silently miss the module-specific LLM/timeout settings.
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.assistant.service import AssistantService
from app.agent.graph import AgentState, ExtractionGraph
from app.core.office_pdf import convert_doc_bytes_to_docx, convert_word_bytes_to_pdf, is_word_file
from app.core.parser import parse_document_in_subprocess
from app.db.storage import ExtractionStorage
from app.schemas import (
    AssistantChatStreamRequest,
    AssistantSessionRequest,
    AssistantSessionResponse,
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

logger = logging.getLogger(__name__)
module4_sync_tasks: Set[asyncio.Task[Any]] = set()
module4_sync_metrics: Dict[str, Any] = {
    "attempted_batches": 0,
    "succeeded_batches": 0,
    "failed_batches": 0,
    "last_error": "",
    "last_success_at": 0.0,
    "last_job_id": "",
    "last_batch_id": "",
    "last_endpoint": "",
    "last_source_batch_key": "",
}


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


@dataclass
class ExtractionJobFileState:
    file_name: str
    file_hash: str
    status: str
    stage: str
    progress_ratio: float
    message: str
    artifact_path: Optional[str] = None
    artifact_url: Optional[str] = None
    error: str = ""
    track: str = ""
    cached: bool = False


@dataclass
class ExtractionJobState:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    total_files: int
    completed_files: int
    failed_files: int
    current_file_index: int
    current_file_name: str
    current_stage: str
    files: List[ExtractionJobFileState]
    documents: List[DocumentExtractionResponse]
    errors: List[str]

    def terminal(self) -> bool:
        return self.status in {"completed", "failed"}


EXTRACTION_CACHE_VERSION = (
    str(os.getenv("MODULE2_EXTRACTION_CACHE_VERSION", "20260309-word-pdf-route-v1")).strip()
    or "20260309-word-pdf-route-v1"
)


class StreamRouter:
    """Layer 1: Ingestion & triage (hash/cache/routing)."""

    def __init__(self, storage: ExtractionStorage) -> None:
        self.storage = storage

    async def triage(self, file_name: str, file_bytes: bytes, schema_hash: str) -> RouteDecision:
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        cache_key = hashlib.sha256(
            f"{EXTRACTION_CACHE_VERSION}:{file_hash}:{schema_hash}".encode("utf-8")
        ).hexdigest()
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
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3002,http://127.0.0.1:3002,http://localhost:5173,http://127.0.0.1:5173",
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
assistant_service = AssistantService(storage)
bridge_jobs: Dict[str, BridgeJobState] = {}
bridge_request_index: Dict[str, str] = {}
bridge_lock = asyncio.Lock()
office_preview_jobs: Dict[str, OfficePreviewJob] = {}
office_preview_lock = asyncio.Lock()
extraction_jobs: Dict[str, ExtractionJobState] = {}
extraction_lock = asyncio.Lock()


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
    if text in {"int", "integer"}:
        return "integer"
    if text in {"number", "float", "double", "numeric", "decimal", "ratio", "percent"}:
        return "number"
    if text in {"date", "datetime", "time", "timestamp"}:
        return "date"
    if text in {"bool", "boolean"}:
        return "boolean"
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


def _repair_latin1_utf8_mojibake(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    try:
        repaired = raw.encode("latin-1").decode("utf-8")
    except Exception:
        return raw
    return repaired if repaired else raw


def _schema_payload_score(schema_obj: Any) -> Tuple[int, int, int]:
    if not isinstance(schema_obj, dict):
        return (-1, -1, -1)
    raw_fields = _schema_target_fields(schema_obj)
    normalized = _normalize_schema_fields(raw_fields, max_fields=max(8, min(64, len(raw_fields) or 8)))
    cjk_hits = sum(
        sum(1 for ch in str(name) if "\u4e00" <= ch <= "\u9fff")
        for name in normalized.keys()
    )
    return (len(normalized), cjk_hits, len(raw_fields))


def _parse_schema_form_json(raw_schema: str) -> Dict[str, Any]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def _add_candidate(text: str) -> None:
        candidate = str(text or "")
        if candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    _add_candidate(raw_schema)
    _add_candidate(_repair_latin1_utf8_mojibake(raw_schema))

    best_obj: Optional[Dict[str, Any]] = None
    best_score: Tuple[int, int, int] = (-1, -1, -1)
    first_json_error: Optional[json.JSONDecodeError] = None
    non_dict_payload: Any = None

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            if first_json_error is None:
                first_json_error = exc
            continue
        if not isinstance(payload, dict):
            if non_dict_payload is None:
                non_dict_payload = payload
            continue
        score = _schema_payload_score(payload)
        if score > best_score:
            best_obj = payload
            best_score = score

    if best_obj is not None:
        return best_obj
    if non_dict_payload is not None:
        raise HTTPException(status_code=400, detail="Schema must be a JSON object")
    if first_json_error is not None:
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {first_json_error}") from first_json_error
    raise HTTPException(status_code=400, detail="Invalid schema JSON")


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


_DATE_FIELD_TOKENS = (
    "日期",
    "时间",
    "年份",
    "年月",
    "季度",
    "时点",
    "date",
    "time",
    "datetime",
    "timestamp",
    "year",
    "month",
)

_INTEGER_FIELD_TOKENS = (
    "数量",
    "总数",
    "个数",
    "条数",
    "件数",
    "人数",
    "家数",
    "座数",
    "项数",
    "单位数",
    "count",
    "quantity",
    "qty",
    "total_count",
    "item_count",
)

_NUMBER_FIELD_TOKENS = (
    "金额",
    "总量",
    "总计",
    "合计",
    "均值",
    "平均",
    "比例",
    "占比",
    "比率",
    "税率",
    "增速",
    "增长",
    "成本",
    "费用",
    "单价",
    "总价",
    "值",
    "分数",
    "指数",
    "监测值",
    "amount",
    "total",
    "ratio",
    "rate",
    "percent",
    "price",
    "cost",
    "value",
    "score",
    "index",
    "avg",
    "average",
)


def _schema_field_type_priority(field_type: str) -> int:
    normalized = _coerce_field_type(field_type)
    return {
        "string": 0,
        "number": 1,
        "integer": 2,
        "date": 2,
        "boolean": 2,
    }.get(normalized, 0)


def _field_name_prefers_date(field_name: str) -> bool:
    text = str(field_name or "").strip().lower()
    if not text:
        return False
    return any(tok in text for tok in _DATE_FIELD_TOKENS)


def _field_name_prefers_integer(field_name: str) -> bool:
    text = str(field_name or "").strip().lower()
    if not text:
        return False
    if _field_name_prefers_date(text):
        return False
    return any(tok in text for tok in _INTEGER_FIELD_TOKENS)


def _field_name_prefers_number(field_name: str) -> bool:
    text = str(field_name or "").strip().lower()
    if not text:
        return False
    if _field_name_prefers_date(text):
        return False
    return any(tok in text for tok in _NUMBER_FIELD_TOKENS)


def _infer_field_type_from_name(field_name: str) -> str:
    if _field_name_prefers_date(field_name):
        return "date"
    if _field_name_prefers_integer(field_name):
        return "integer"
    if _field_name_prefers_number(field_name):
        return "number"
    return "string"


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
        inferred = _infer_field_type_from_name(key)
        prev_type = type_map.get(key)
        if prev_type is None or _schema_field_type_priority(inferred) > _schema_field_type_priority(prev_type):
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
            -_schema_field_type_priority(type_map.get(name, "string")),
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
    provider = getattr(graph, "_provider", None)
    llm = getattr(graph, "llm", None)
    if provider is None and llm is None:
        return {}

    is_xlsx = file_name.lower().endswith(".xlsx")
    context = _extract_text_for_schema(markdown, table_blocks, max_chars=4200 if is_xlsx else 9000)
    if not context:
        return {}

    system_prompt = (
        "You are a document schema planner. Select only the most valuable, stable, and extractable fields from the file. "
        "Prefer identifiers, dates, organizations, people, regions, totals, counts, rates, units, and the core business metrics. "
        "For spreadsheets or table-heavy documents, prioritize main dimensions and key metrics instead of generic helper columns. "
        "Avoid low-value generic fields such as ref, page, text, 序号, 备注, 说明, name, or sheet unless they are true business fields. "
        f"Return 4 to {max(4, min(max_fields, 12))} fields, JSON only, with no explanation."
    )
    user_prompt = (
        f"File name: {file_name}\n"
        f"Document context:\n{context}\n\n"
        "Output JSON exactly as:\n"
        "{\n"
        '  "fields": [\n'
        '    {"field_name": "字段名", "field_type": "string|number|integer|date"},\n'
        "    ...\n"
        "  ]\n"
        "}\n\n"
        "Keep field names in the original document language whenever possible."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    timeout_sec = max(6.0, float(os.getenv("MODULE2_AUTO_SCHEMA_LLM_TIMEOUT_SEC", "90")))
    max_output_tokens = max(512, int(os.getenv("MODULE2_AUTO_SCHEMA_LLM_MAX_TOKENS", "1400")))
    try:
        if provider is not None:
            payload = await asyncio.wait_for(
                graph.invoke_json_object(
                    messages,
                    max_tokens=max_output_tokens,
                    purpose="schema_planner",
                ),
                timeout=timeout_sec,
            )
        else:
            invoke_coro = llm.ainvoke(messages)
            raw_resp = await asyncio.wait_for(invoke_coro, timeout=timeout_sec)

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
    except Exception:
        return {}

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
    elif file_name.lower().endswith(".pdf"):
        max_fields = min(
            max_fields,
            max(4, int(os.getenv("MODULE2_AUTO_SCHEMA_PDF_MAX_FIELDS", "8"))),
        )
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


def _write_json_artifact(*, payload: Dict[str, Any], file_name: str, sub_dir: str) -> Tuple[str, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _write_artifact_bytes(data=data, file_name=file_name, sub_dir=sub_dir, ext=".json")


def _persist_assistant_payload_artifact(
    *,
    file_name: str,
    file_hash: str,
    table_blocks: List[Dict[str, Any]],
    figure_blocks: List[Dict[str, Any]],
) -> Tuple[str, str]:
    payload = {
        "version": "module2-assistant-payload-v1",
        "file_name": file_name,
        "file_hash": file_hash,
        "tables": table_blocks,
        "figures": figure_blocks,
    }
    try:
        return _write_json_artifact(
            payload=payload,
            file_name=f"{Path(file_name).stem}_assistant_payload",
            sub_dir=f"assistant_payload/{file_hash[:12]}",
        )
    except Exception as exc:
        logger.warning("failed to persist assistant payload artifact for %s: %s", file_name, exc)
        return "", ""


def _office_preview_timeout_sec() -> float:
    return max(20.0, float(os.getenv("MODULE2_OFFICE_PREVIEW_TIMEOUT_SEC", "120")))


def _office_convert_enabled() -> bool:
    return (os.getenv("MODULE2_DOC_TO_PDF_ENABLE", "true") or "true").lower() in {"1", "true", "yes"}


def _word_pdf_required() -> bool:
    raw = (
        os.getenv(
            "MODULE2_WORD_PARSE_VIA_PDF",
            os.getenv("MODULE2_WORD_REQUIRE_PDF_PARSE", "true"),
        )
        or "true"
    ).lower()
    return raw in {"1", "true", "yes"}


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


def _office_preview_artifact_exists(job: OfficePreviewJob) -> bool:
    fragment = _artifact_fragment_from_path(job.artifact_path)
    if not fragment:
        raw_url = str(job.artifact_url or "").strip()
        prefix = "/extract/artifact/"
        if raw_url.startswith(prefix):
            fragment = urllib.parse.unquote(raw_url[len(prefix) :]).strip().strip("/")
    if not fragment:
        return False
    root = _artifact_root_dir()
    try:
        target = (root / fragment).resolve()
        target.relative_to(root)
    except Exception:
        return False
    return target.exists() and target.is_file()


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


def _serialize_extraction_job(job: ExtractionJobState, *, include_documents: bool = False) -> Dict[str, Any]:
    total_files = max(1, int(job.total_files or 0))
    progress_ratio = sum(
        max(0.0, min(1.0, float(item.progress_ratio or 0.0))) for item in job.files
    ) / float(total_files)
    payload: Dict[str, Any] = {
        "ok": True,
        "job_id": job.job_id,
        "status": job.status,
        "terminal": job.terminal(),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "progress": {
            "total_files": int(job.total_files),
            "completed_files": int(job.completed_files),
            "failed_files": int(job.failed_files),
            "current_file_index": int(job.current_file_index),
            "current_file_name": job.current_file_name,
            "current_stage": job.current_stage,
            "progress_ratio": round(progress_ratio, 4),
        },
        "files": [
            {
                "file_name": item.file_name,
                "file_hash": item.file_hash,
                "status": item.status,
                "stage": item.stage,
                "progress_ratio": round(max(0.0, min(1.0, float(item.progress_ratio or 0.0))), 4),
                "message": item.message,
                "artifact_path": item.artifact_path,
                "artifact_url": item.artifact_url,
                "error": item.error,
                "track": item.track,
                "cached": bool(item.cached),
            }
            for item in job.files
        ],
        "errors": list(job.errors),
    }
    if include_documents or job.terminal():
        payload["documents"] = [doc.model_dump(mode="json") for doc in job.documents]
    return payload


def _extraction_job_ttl_sec() -> float:
    return max(300.0, float(os.getenv("MODULE2_EXTRACT_JOB_TTL_SEC", "7200")))


def _extraction_job_cap() -> int:
    return max(16, int(os.getenv("MODULE2_EXTRACT_JOB_CAP", "240")))


def _cleanup_extraction_jobs_locked() -> None:
    ttl_sec = _extraction_job_ttl_sec()
    cap = _extraction_job_cap()
    now_ts = time.time()
    expired = [
        job_id
        for job_id, job in extraction_jobs.items()
        if job.terminal() and (now_ts - float(job.updated_at)) > ttl_sec
    ]
    for job_id in expired:
        extraction_jobs.pop(job_id, None)
    if len(extraction_jobs) <= cap:
        return
    ordered = sorted(extraction_jobs.values(), key=lambda item: float(item.updated_at))
    for item in ordered[: max(0, len(extraction_jobs) - cap)]:
        extraction_jobs.pop(item.job_id, None)


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


def _trace_display_kind_from_hit(hit: Dict[str, Any]) -> str:
    object_type = str(hit.get("object_type", "") or "").strip().lower()
    if object_type in {"field", "table"}:
        return object_type
    if object_type != "figure":
        return "other"

    locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
    figure_type = str(locator.get("figure_type", "")).strip().lower()
    if figure_type in {"table", "spreadsheet"}:
        return "table"

    content_modes = [
        str(item).strip().lower()
        for item in (locator.get("content_modes") if isinstance(locator.get("content_modes"), list) else [])
        if str(item).strip()
    ]
    dataframe = locator.get("dataframe") if isinstance(locator.get("dataframe"), dict) else {}
    headers = dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else []
    rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
    has_headers = any(str(cell).strip() for cell in headers)
    has_rows = any(isinstance(row, list) and any(str(cell).strip() for cell in row) for row in rows[:3])
    if (has_headers or has_rows) and "visual" not in content_modes and "topology" not in content_modes:
        return "table"
    return "image"


def _trace_stats(trace_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    count_by_type: Dict[str, int] = {}
    count_by_display_kind: Dict[str, int] = {}
    page_set = set()
    for hit in trace_hits:
        typ = str(hit.get("object_type", "unknown") or "unknown")
        count_by_type[typ] = count_by_type.get(typ, 0) + 1
        display_kind = _trace_display_kind_from_hit(hit)
        count_by_display_kind[display_kind] = count_by_display_kind.get(display_kind, 0) + 1
        try:
            page_no = int(hit.get("page", 0) or 0)
        except (TypeError, ValueError):
            page_no = 0
        if page_no > 0:
            page_set.add(page_no)
    return {
        "trace_hit_count": len(trace_hits),
        "trace_object_counts": count_by_type,
        "trace_display_counts": count_by_display_kind,
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
    extract_default = max(8.0, float(os.getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "150")))
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


def _strip_recovered_extract_warnings(warnings: List[str], *, quality_ok: bool, quick_fallback: bool) -> List[str]:
    if not quality_ok or quick_fallback:
        return _normalize_soft_warnings(warnings)
    noisy_prefixes = (
        "table_extract_error:",
        "field_extract_error:",
        "table_extract_timeout:",
        "field_extract_timeout:",
    )
    return _normalize_soft_warnings(
        [item for item in warnings if not any(str(item or "").startswith(prefix) for prefix in noisy_prefixes)]
    )


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


def _absolute_artifact_storage_path(path_fragment: str) -> str:
    fragment = str(path_fragment or "").strip()
    if not fragment:
        return ""
    try:
        return str(_safe_artifact_path(fragment))
    except HTTPException:
        return ""


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


def _module4_sync_enabled() -> bool:
    return (os.getenv("MODULE2_MODULE4_SYNC_ENABLED", "true") or "true").lower() in {"1", "true", "yes"}


def _module4_base_url() -> str:
    raw = (os.getenv("MODULE2_MODULE4_BASE_URL", "http://localhost:8100") or "").strip().rstrip("/")
    return raw or "http://localhost:8100"


def _module4_sync_timeout_sec() -> float:
    return max(2.0, float(os.getenv("MODULE2_MODULE4_SYNC_TIMEOUT_SEC", "12")))


def _module4_sync_retries() -> int:
    return max(0, min(int(os.getenv("MODULE2_MODULE4_SYNC_RETRIES", "2")), 5))


def _module4_sync_backoff_sec() -> float:
    return max(0.2, float(os.getenv("MODULE2_MODULE4_SYNC_BACKOFF_SEC", "1.5")))


def _module4_sync_shutdown_drain_sec() -> float:
    return max(0.0, float(os.getenv("MODULE2_MODULE4_SHUTDOWN_DRAIN_SEC", "8")))


def _module4_default_tenant() -> str:
    return (os.getenv("MODULE2_MODULE4_DEFAULT_TENANT", "default") or "default").strip() or "default"


def _module4_tenant(request: Optional[Request] = None, explicit: str = "") -> str:
    explicit_clean = (explicit or "").strip()
    if explicit_clean:
        return explicit_clean
    if request is not None:
        header_tenant = (request.headers.get("x-tenant-id") or "").strip()
        if header_tenant:
            return header_tenant
    return _module4_default_tenant()


def _module4_headers(tenant_id: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json", "X-Tenant-Id": tenant_id}
    bearer = (os.getenv("MODULE2_MODULE4_BEARER_TOKEN", "") or "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _module4_sync_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _module4_sync_delay_sec(attempt_index: int) -> float:
    base = _module4_sync_backoff_sec()
    return min(base * (2 ** max(0, attempt_index - 1)), 12.0)


def _track_module4_sync_task(task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    module4_sync_tasks.add(task)

    def _cleanup(done: asyncio.Task[Any]) -> None:
        module4_sync_tasks.discard(done)
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("module2 module4 sync task crashed: %s: %s", type(exc).__name__, exc)

    task.add_done_callback(_cleanup)
    return task


def _spawn_module4_sync_task(*, source: str, tenant_id: str, documents: List[Any], source_batch_key: str) -> None:
    _track_module4_sync_task(
        asyncio.create_task(
            _sync_documents_to_module4(
                source=source,
                tenant_id=tenant_id,
                documents=documents,
                source_batch_key=source_batch_key,
            )
        )
    )


def _spawn_module4_upload_sync_task(*, source: str, tenant_id: str, uploads: List[Dict[str, Any]], source_batch_key: str) -> None:
    _track_module4_sync_task(
        asyncio.create_task(
            _sync_uploads_to_module4(
                source=source,
                tenant_id=tenant_id,
                uploads=uploads,
                source_batch_key=source_batch_key,
            )
        )
    )


def _module4_normalize_documents(documents: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in documents:
        if hasattr(item, "model_dump"):
            raw = item.model_dump(mode="json")
        elif isinstance(item, dict):
            raw = dict(item)
        else:
            continue
        normalized.append(raw if isinstance(raw, dict) else {})
    return normalized


def _module4_normalize_uploads(uploads: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in uploads:
        if isinstance(item, dict):
            raw = dict(item)
        elif hasattr(item, "model_dump"):
            raw = item.model_dump(mode="json")
        else:
            continue
        normalized.append(raw if isinstance(raw, dict) else {})
    return normalized


def _module4_source_batch_key(
    *,
    source: str,
    tenant_id: str,
    documents: List[Any],
    seed: str,
) -> str:
    payload = {
        "source": source,
        "tenant_id": tenant_id,
        "seed": seed,
        "documents": _module4_normalize_documents(documents),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return digest[:32]


def _module4_upload_source_batch_key(
    *,
    source: str,
    tenant_id: str,
    uploads: List[Any],
    seed: str,
) -> str:
    payload = {
        "source": source,
        "tenant_id": tenant_id,
        "seed": seed,
        "uploads": [
            {
                "file_name": item.get("file_name"),
                "file_hash": item.get("file_hash"),
                "artifact_path": item.get("artifact_path"),
                "storage_path": item.get("storage_path"),
            }
            for item in _module4_normalize_uploads(uploads)
        ],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return digest[:32]


async def _sync_documents_to_module4(
    *,
    source: str,
    tenant_id: str,
    documents: List[Any],
    source_batch_key: str,
) -> None:
    if not _module4_sync_enabled():
        return

    normalized_docs = _module4_normalize_documents(documents)
    if not normalized_docs:
        return
    module4_sync_metrics["attempted_batches"] = int(module4_sync_metrics.get("attempted_batches", 0)) + 1

    payload = {
        "tenant_id": tenant_id,
        "source": source,
        "source_batch_key": source_batch_key,
        "documents": normalized_docs,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{_module4_base_url()}/module4/ingest"
    headers = _module4_headers(tenant_id)
    timeout_sec = _module4_sync_timeout_sec()
    attempts = _module4_sync_retries() + 1

    def _post() -> Tuple[int, str]:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), body

    for attempt in range(1, attempts + 1):
        try:
            status, body = await asyncio.to_thread(_post)
            if status >= 400:
                raise RuntimeError(f"HTTP {status}: {body[:300]}")
            response_payload: Dict[str, Any] = {}
            try:
                loaded = json.loads(body)
                if isinstance(loaded, dict):
                    response_payload = loaded
            except Exception:
                response_payload = {}
            module4_sync_metrics["succeeded_batches"] = int(module4_sync_metrics.get("succeeded_batches", 0)) + 1
            module4_sync_metrics["last_error"] = ""
            module4_sync_metrics["last_success_at"] = time.time()
            module4_sync_metrics["last_job_id"] = str(response_payload.get("job_id") or "")
            module4_sync_metrics["last_batch_id"] = str(response_payload.get("batch_id") or "")
            module4_sync_metrics["last_endpoint"] = "/module4/ingest"
            module4_sync_metrics["last_source_batch_key"] = str(source_batch_key or "")
            logger.info(
                "module2 synced %s document(s) to module4 tenant=%s source=%s batch=%s attempt=%s/%s",
                len(normalized_docs),
                tenant_id,
                source,
                source_batch_key,
                attempt,
                attempts,
            )
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            retryable = _module4_sync_retryable_status(int(getattr(exc, "code", 0) or 0))
            message = f"HTTPError {getattr(exc, 'code', 'unknown')}: {detail[:400]}"
            if attempt < attempts and retryable:
                delay = _module4_sync_delay_sec(attempt)
                logger.warning(
                    "module2 -> module4 sync failed, retrying in %.1fs (%s/%s): %s",
                    delay,
                    attempt,
                    attempts,
                    message,
                )
                await asyncio.sleep(delay)
                continue
            module4_sync_metrics["failed_batches"] = int(module4_sync_metrics.get("failed_batches", 0)) + 1
            module4_sync_metrics["last_error"] = message
            logger.warning("module2 -> module4 sync failed: %s", message)
            return
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                delay = _module4_sync_delay_sec(attempt)
                logger.warning(
                    "module2 -> module4 sync exception, retrying in %.1fs (%s/%s): %s",
                    delay,
                    attempt,
                    attempts,
                    message,
                )
                await asyncio.sleep(delay)
                continue
            module4_sync_metrics["failed_batches"] = int(module4_sync_metrics.get("failed_batches", 0)) + 1
            module4_sync_metrics["last_error"] = message[:400]
            logger.warning("module2 -> module4 sync failed: %s", message)
            return


async def _sync_uploads_to_module4(
    *,
    source: str,
    tenant_id: str,
    uploads: List[Dict[str, Any]],
    source_batch_key: str,
) -> None:
    if not _module4_sync_enabled():
        return

    normalized_uploads = _module4_normalize_uploads(uploads)
    if not normalized_uploads:
        return
    module4_sync_metrics["attempted_batches"] = int(module4_sync_metrics.get("attempted_batches", 0)) + 1

    payload = {
        "tenant_id": tenant_id,
        "source": source,
        "source_batch_key": source_batch_key,
        "graph_mode": "hybrid",
        "uploads": normalized_uploads,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{_module4_base_url()}/module4/sync/uploads"
    headers = _module4_headers(tenant_id)
    timeout_sec = _module4_sync_timeout_sec()
    attempts = _module4_sync_retries() + 1

    def _post() -> Tuple[int, str]:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), body

    for attempt in range(1, attempts + 1):
        try:
            status, body = await asyncio.to_thread(_post)
            if status >= 400:
                raise RuntimeError(f"HTTP {status}: {body[:300]}")
            response_payload: Dict[str, Any] = {}
            try:
                loaded = json.loads(body)
                if isinstance(loaded, dict):
                    response_payload = loaded
            except Exception:
                response_payload = {}
            module4_sync_metrics["succeeded_batches"] = int(module4_sync_metrics.get("succeeded_batches", 0)) + 1
            module4_sync_metrics["last_error"] = ""
            module4_sync_metrics["last_success_at"] = time.time()
            module4_sync_metrics["last_job_id"] = str(response_payload.get("job_id") or "")
            module4_sync_metrics["last_batch_id"] = str(response_payload.get("batch_id") or "")
            module4_sync_metrics["last_endpoint"] = "/module4/sync/uploads"
            module4_sync_metrics["last_source_batch_key"] = str(source_batch_key or "")
            logger.info(
                "module2 synced %s upload(s) to module4 tenant=%s source=%s batch=%s attempt=%s/%s",
                len(normalized_uploads),
                tenant_id,
                source,
                source_batch_key,
                attempt,
                attempts,
            )
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            retryable = _module4_sync_retryable_status(int(getattr(exc, "code", 0) or 0))
            message = f"HTTPError {getattr(exc, 'code', 'unknown')}: {detail[:400]}"
            if attempt < attempts and retryable:
                delay = _module4_sync_delay_sec(attempt)
                logger.warning(
                    "module2 -> module4 upload sync failed, retrying in %.1fs (%s/%s): %s",
                    delay,
                    attempt,
                    attempts,
                    message,
                )
                await asyncio.sleep(delay)
                continue
            module4_sync_metrics["failed_batches"] = int(module4_sync_metrics.get("failed_batches", 0)) + 1
            module4_sync_metrics["last_error"] = message
            logger.warning("module2 -> module4 upload sync failed: %s", message)
            return
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                delay = _module4_sync_delay_sec(attempt)
                logger.warning(
                    "module2 -> module4 upload sync exception, retrying in %.1fs (%s/%s): %s",
                    delay,
                    attempt,
                    attempts,
                    message,
                )
                await asyncio.sleep(delay)
                continue
            module4_sync_metrics["failed_batches"] = int(module4_sync_metrics.get("failed_batches", 0)) + 1
            module4_sync_metrics["last_error"] = message[:400]
            logger.warning("module2 -> module4 upload sync failed: %s", message)
            return


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


def _summarize_document_payload_legacy(req: SummarizeRequest) -> str:
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


def _summary_clean_text(value: Any, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("，,；;。 ") + "…"


def _summary_unique_texts(values: List[Any], limit: int = 4, max_len: int = 80) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for value in values:
        cleaned = _summary_clean_text(value, max_len=max_len)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _summary_trace_hit_dicts(req: SummarizeRequest) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for item in req.trace_hits or []:
        if isinstance(item, dict):
            hits.append(dict(item))
            continue
        if hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
            if isinstance(payload, dict):
                hits.append(payload)
    return hits


def _summary_trace_kind(hit: Dict[str, Any]) -> str:
    return _trace_display_kind_from_hit(hit)


_SUMMARY_NOTICE_SKIP = {
    "quality_gate_ok",
}

_SUMMARY_NOTICE_MAP = {
    "table_extract_timeout": "复杂表格抽取超时，当前表格结果可能仍有遗漏。",
    "field_extract_timeout": "字段抽取超时，部分字段可能尚未完全识别。",
    "field_extract_error": "字段抽取阶段出现异常，部分字段可能尚未完全识别。",
    "word_pdf_parse_timeout_fallback_fasttrack": "Word 转 PDF 后的深度版面解析超时，当前已切换为快速解析链路，图表完整度可能受影响。",
    "pdf_visual_timeout_fallback_fasttrack": "PDF 视觉解析超时，当前已切换为快速解析链路，复杂版面定位可能不够完整。",
}


def _summary_notice_text(raw_notice: Any) -> str:
    text = str(raw_notice or "").strip()
    if not text or text in _SUMMARY_NOTICE_SKIP:
        return ""
    for prefix, mapped in _SUMMARY_NOTICE_MAP.items():
        if text == prefix or text.startswith(f"{prefix}:"):
            return mapped
    return _summary_clean_text(text, max_len=64)


def _summarize_document_payload(req: SummarizeRequest) -> str:
    lines: List[str] = [f"文档《{req.file_name}》已完成内容解析。"]

    result_items: List[str] = []
    for key, value in req.result.items():
        if not isinstance(value, dict):
            continue
        field_val = value.get("value")
        if field_val in (None, "", [], {}):
            continue
        field_text = _summary_clean_text(field_val, max_len=42)
        if not field_text:
            continue
        label = _FIELD_LABELS.get(key, key)
        conf = value.get("confidence")
        try:
            conf_pct = int(round(float(conf or 0.0) * 100))
        except Exception:
            conf_pct = 0
        if conf_pct > 0:
            result_items.append(f"{label}为{field_text}（置信度{conf_pct}%）")
        else:
            result_items.append(f"{label}为{field_text}")
        if len(result_items) >= 6:
            break
    if result_items:
        lines.append("已抽取的关键信息包括：" + "；".join(result_items) + "。")

    trace_hits = _summary_trace_hit_dicts(req)
    content_focus_raw: List[str] = []
    table_focus_raw: List[str] = []
    image_focus_raw: List[str] = []
    trace_table_ids: Set[str] = set()
    trace_image_ids: Set[str] = set()

    for hit in trace_hits:
        kind = _summary_trace_kind(hit)
        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
        object_id = str(hit.get("object_id", "")).strip()
        object_key = object_id.lower()
        object_unique_key = object_key or str(hit.get("ref_id", "")).strip() or _summary_clean_text(hit.get("snippet"), max_len=48)
        snippet = _summary_clean_text(hit.get("snippet"), max_len=72)

        if kind == "field":
            if snippet:
                label = _FIELD_LABELS.get(object_key, object_id) if object_key else object_id
                content_focus_raw.append(f"{label}：{snippet}" if label else snippet)
            continue

        if kind == "table":
            if object_unique_key:
                trace_table_ids.add(object_unique_key)
            sheet_name = _summary_clean_text(locator.get("sheet_name"), max_len=24)
            table_preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}
            headers_raw = table_preview.get("headers") if isinstance(table_preview.get("headers"), list) else []
            headers = _summary_unique_texts(headers_raw, limit=3, max_len=18)
            if headers:
                header_text = " / ".join(headers)
                table_focus_raw.append(f"{sheet_name}表格包含 {header_text}" if sheet_name else f"表格包含 {header_text}")
            elif snippet:
                table_focus_raw.append(snippet)
            continue

        if kind == "image":
            if object_unique_key:
                trace_image_ids.add(object_unique_key)
            caption = _summary_clean_text(locator.get("caption"), max_len=64)
            key_points = _summary_unique_texts(
                locator.get("key_points") if isinstance(locator.get("key_points"), list) else [],
                limit=2,
                max_len=48,
            )
            text_blocks = _summary_unique_texts(
                locator.get("text_blocks") if isinstance(locator.get("text_blocks"), list) else [],
                limit=2,
                max_len=48,
            )
            image_focus_raw.append(caption or (key_points[0] if key_points else "") or (text_blocks[0] if text_blocks else "") or snippet)

    content_focus = _summary_unique_texts(content_focus_raw, limit=3, max_len=78)
    if content_focus:
        lines.append("从原文与溯源片段看，文档重点涉及：" + "；".join(content_focus) + "。")

    table_focus = _summary_unique_texts(table_focus_raw, limit=2, max_len=54)
    image_focus = _summary_unique_texts(image_focus_raw, limit=2, max_len=54)

    diag = req.diagnostics or {}
    trace_display_counts = diag.get("trace_display_counts") if isinstance(diag.get("trace_display_counts"), dict) else {}
    table_count = int(diag.get("table_count", 0) or 0)
    image_count = int(diag.get("figure_count", 0) or 0)
    table_count = max(table_count, len(trace_table_ids), int(trace_display_counts.get("table", 0) or 0))
    image_count = max(image_count, len(trace_image_ids), int(trace_display_counts.get("image", 0) or 0))

    structure_parts: List[str] = []
    if table_count > 0:
        table_part = f"{table_count} 个表格"
        if table_focus:
            table_part += f"（如：{'；'.join(table_focus)}）"
        structure_parts.append(table_part)
    if image_count > 0:
        image_part = f"{image_count} 处图片"
        if image_focus:
            image_part += f"（如：{'；'.join(image_focus)}）"
        structure_parts.append(image_part)
    if structure_parts:
        lines.append("识别到的结构内容包括" + "，".join(structure_parts) + "。")

    if not result_items and not content_focus and not structure_parts:
        lines.append("当前已完成基础解析，但尚未形成足够稳定的内容摘要，建议结合抽取结果与溯源定位继续查看。")

    notices: List[str] = []
    error_items = _summary_unique_texts(
        [_summary_notice_text(item) for item in (req.errors or []) if _summary_notice_text(item)],
        limit=2,
        max_len=64,
    )
    warning_items = _summary_unique_texts(
        [_summary_notice_text(item) for item in (req.soft_warnings or []) if _summary_notice_text(item)],
        limit=2,
        max_len=64,
    )
    if error_items:
        notices.append("需关注：" + "；".join(error_items))
    if warning_items:
        notices.append("提示：" + "；".join(warning_items))
    if notices:
        lines.append(" ".join(notices) + "。")

    summary = " ".join(line.strip() for line in lines if line and line.strip()).strip()
    max_chars = int(req.max_chars or 400)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


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
    if module4_sync_tasks:
        pending = list(module4_sync_tasks)
        drain_timeout = _module4_sync_shutdown_drain_sec()
        if drain_timeout > 0:
            _, still_pending = await asyncio.wait(pending, timeout=drain_timeout)
            if still_pending:
                for task in still_pending:
                    task.cancel()
                await asyncio.gather(*still_pending, return_exceptions=True)
        else:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
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


async def _convert_doc_to_docx_with_timeout(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float,
) -> Tuple[bytes, Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(
            None,
            lambda: convert_doc_bytes_to_docx(
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
    progress_hook: Optional[Callable[[str, float, str, Dict[str, Any]], None]] = None,
) -> DocumentExtractionResponse:
    t0 = time.perf_counter()
    router = StreamRouter(storage)
    decision = await router.triage(file_name, file_bytes, schema_hash)

    def _emit_progress(stage: str, ratio: float, message: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        if progress_hook is None:
            return
        try:
            progress_hook(
                str(stage or "").strip() or "running",
                max(0.0, min(1.0, float(ratio))),
                str(message or "").strip(),
                dict(extra or {}),
            )
        except Exception:
            return

    if decision.cached_payload is not None:
        _emit_progress("cached", 1.0, "命中缓存，正在恢复抽取结果")
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
        cached_diag = dict(cached_diag_raw) if isinstance(cached_diag_raw, dict) else {}
        cached_tables = decision.cached_payload.get("tables") if isinstance(decision.cached_payload.get("tables"), list) else []
        cached_figures = decision.cached_payload.get("figures") if isinstance(decision.cached_payload.get("figures"), list) else []
        if (cached_tables or cached_figures) and not str(cached_diag.get("assistant_payload_artifact_path") or "").strip():
            artifact_path, artifact_url = _persist_assistant_payload_artifact(
                file_name=file_name,
                file_hash=decision.file_hash,
                table_blocks=cached_tables,
                figure_blocks=cached_figures,
            )
            if artifact_path:
                cached_diag["assistant_payload_artifact_path"] = artifact_path
                cached_diag["assistant_payload_artifact_url"] = artifact_url
                cached_diag["assistant_payload_version"] = "module2-assistant-payload-v1"
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

    _emit_progress("preflight", 0.05, "已接收文件，正在执行预检查")
    loop = asyncio.get_running_loop()
    parse_timeout_sec = max(5.0, float(os.getenv("MODULE2_PARSE_TIMEOUT_SEC", "150")))
    extract_timeout_sec = max(8.0, float(os.getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "150")))
    nonpdf_preflight: Optional[Dict[str, Any]] = None
    nonpdf_budget: Optional[Dict[str, float]] = None
    nonpdf_total_budget_sec: Optional[float] = None
    nonpdf_guard_sec = max(1.0, float(os.getenv("MODULE2_NONPDF_BUDGET_GUARD_SEC", "2.0")))
    word_parse_extract_budget_sec: Optional[float] = None
    word_convert_budget_sec: Optional[float] = None
    word_parse_via_pdf = _word_pdf_required()
    if not file_name.lower().endswith(".pdf"):
        nonpdf_preflight = _preflight_nonpdf_profile(file_name=file_name, file_bytes=file_bytes)
        nonpdf_budget = _resolve_nonpdf_budgets(str(nonpdf_preflight.get("profile", "mixed")))
        parse_timeout_sec = float(nonpdf_budget["parse_timeout_sec"])
        extract_timeout_sec = float(nonpdf_budget["extract_timeout_sec"])
        nonpdf_total_budget_sec = float(nonpdf_budget.get("total_budget_sec", 90.0))
        if file_name.lower().endswith(".xlsx"):
            parse_timeout_sec = max(
                parse_timeout_sec,
                float(os.getenv("MODULE2_XLSX_PARSE_TIMEOUT_SEC", "32")),
            )
            extract_timeout_sec = max(
                extract_timeout_sec,
                float(os.getenv("MODULE2_XLSX_EXTRACT_TIMEOUT_SEC", "96")),
            )
            nonpdf_total_budget_sec = max(
                nonpdf_total_budget_sec,
                float(os.getenv("MODULE2_XLSX_TOTAL_BUDGET_SEC", "140")),
            )
        if is_word_file(file_name):
            nonpdf_total_budget_sec = max(
                nonpdf_total_budget_sec or 0.0,
                float(os.getenv("MODULE2_WORD_TOTAL_BUDGET_SEC", "150")),
            )
            parse_timeout_sec = max(
                parse_timeout_sec,
                float(os.getenv("MODULE2_WORD_PARSE_TIMEOUT_SEC", "42")),
            )
            extract_timeout_sec = max(
                extract_timeout_sec,
                float(os.getenv("MODULE2_WORD_EXTRACT_TIMEOUT_SEC", "72")),
            )
            word_parse_extract_budget_sec = max(
                32.0,
                float(os.getenv("MODULE2_WORD_PARSE_EXTRACT_BUDGET_SEC", "96")),
            )
            word_convert_budget_sec = max(15.0, float(os.getenv("MODULE2_WORD_CONVERT_BUDGET_SEC", "30")))
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
            # Word preprocessing can be the bottleneck; reserve more parse budget to reduce hard timeouts.
            if parse_extract_total > 12.0:
                target_parse_share = max(
                    0.42,
                    min(0.78, float(os.getenv("MODULE2_WORD_PARSE_SHARE", "0.50"))),
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
                min_word_extract_timeout = max(
                    24.0,
                    float(os.getenv("MODULE2_WORD_EXTRACT_TIMEOUT_MIN_SEC", "56")),
                )
                if extract_timeout_sec < min_word_extract_timeout:
                    parse_timeout_sec = max(
                        min_word_parse_timeout,
                        parse_extract_total - min_word_extract_timeout,
                    )
                    extract_timeout_sec = max(8.0, parse_extract_total - parse_timeout_sec)

    # Keep the outer graph timeout from being lower than the inner field-extraction timeout,
    # otherwise non-PDF flows can terminate the graph before the provider call finishes.
    extract_timeout_sec = max(
        extract_timeout_sec,
        max(8.0, float(os.getenv("MODULE2_FIELD_EXTRACT_TIMEOUT_SEC", "90"))),
    )

    parse_t0 = time.perf_counter()
    parse_track = decision.track
    parse_warning: Optional[str] = None
    figure_blocks: List[Dict[str, Any]] = []
    parse_stats: Dict[str, Any] = {}
    parse_input_name = file_name
    parse_input_bytes = file_bytes
    conversion_diag: Dict[str, Any] = {}

    word_suffix = Path(file_name).suffix.lower()
    if is_word_file(file_name):
        if word_parse_via_pdf and not _office_convert_enabled():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Word 转 PDF 功能已禁用，当前配置要求 DOC/DOCX 必须先转为 PDF 后再解析。"
                ),
            )
        if (not word_parse_via_pdf) and word_suffix == ".doc" and not _office_convert_enabled():
            raise HTTPException(
                status_code=503,
                detail="DOC 原生解析需要启用 Office 转换能力（用于 DOC->DOCX 预处理）。",
            )

    if is_word_file(file_name) and word_parse_via_pdf and _office_convert_enabled():
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
            _emit_progress("converting", 0.14, "正在将文档转换为 PDF 解析链路")
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
            _emit_progress("converting", 0.24, "文档已转换为 PDF，正在准备版面解析")
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
                and (os.getenv("MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK", "false").lower() in {"1", "true", "yes"})
            )
            if (word_parse_via_pdf and not allow_native_fallback) or suffix == ".doc":
                raise HTTPException(
                    status_code=422,
                    detail=f"Word 转 PDF 失败，无法处理 {file_name}: {type(exc).__name__}: {exc}",
                ) from exc
            parse_track = "FastTrack"
            parse_input_name = file_name
            parse_input_bytes = file_bytes
            parse_warning = f"doc_to_pdf_fallback_native:{type(exc).__name__}"
    elif is_word_file(file_name) and (not word_parse_via_pdf):
        parse_track = "FastTrack"
        if word_suffix == ".doc":
            convert_timeout_default = max(12.0, float(os.getenv("MODULE2_DOC_TO_DOCX_TIMEOUT_SEC", "45")))
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
                        detail=f"Non-PDF budget exhausted before DOC->DOCX conversion for {file_name}",
                    )
            convert_timeout_sec = max(12.0, convert_timeout_sec)
            convert_t0 = time.perf_counter()
            try:
                docx_bytes, convert_meta = await _convert_doc_to_docx_with_timeout(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    timeout_sec=convert_timeout_sec,
                )
                parse_input_name = f"{Path(file_name).stem}.docx"
                parse_input_bytes = docx_bytes
                conversion_diag = {
                    "doc_to_docx_converted": True,
                    "doc_to_docx_converter": str(convert_meta.get("converter", "")),
                    "doc_to_docx_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
                    "doc_to_docx_timeout_sec": round(convert_timeout_sec, 3),
                    "doc_to_docx_total_ms": int((time.perf_counter() - convert_t0) * 1000),
                }
            except Exception as exc:
                conversion_diag = {
                    "doc_to_docx_converted": False,
                    "doc_to_docx_error": f"{type(exc).__name__}: {exc}",
                    "doc_to_docx_timeout_sec": round(convert_timeout_sec, 3),
                    "doc_to_docx_total_ms": int((time.perf_counter() - convert_t0) * 1000),
                }
                raise HTTPException(
                    status_code=422,
                    detail=f"DOC 转 DOCX 失败，无法处理 {file_name}: {type(exc).__name__}: {exc}",
                ) from exc

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

    if parse_track == "VisualTrack" and parse_input_name.lower().endswith(".pdf"):
        parse_timeout_sec = max(
            parse_timeout_sec,
            float(
                os.getenv(
                    "MODULE2_PDF_VISUAL_PARSE_TIMEOUT_SEC",
                    os.getenv("MODULE2_MINERU_TIMEOUT_SEC", "900"),
                )
            ),
        )

    _emit_progress("parsing", 0.32, f"正在解析文档版面：{parse_input_name}")
    try:
        parsed_output = await asyncio.wait_for(
            loop.run_in_executor(process_pool, parse_document_in_subprocess, parse_input_bytes, parse_input_name, parse_track),
            timeout=parse_timeout_sec,
        )
        marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
    except TimeoutError as exc:
        parse_input_is_pdf = parse_input_name.lower().endswith(".pdf")
        is_word_pdf_parse = is_word_file(file_name) and parse_input_is_pdf
        should_try_pdf_native_fallback = parse_track == "VisualTrack" and parse_input_is_pdf
        if is_word_pdf_parse or should_try_pdf_native_fallback:
            if is_word_pdf_parse:
                fallback_timeout = max(20.0, min(120.0, parse_timeout_sec * 1.15))
                fallback_input_bytes = parse_input_bytes
                fallback_input_name = parse_input_name
                fallback_track = "VisualTrack->WordPdfFastTrackFallback"
                fallback_hint = "word_pdf_parse_timeout_fallback_fasttrack"
            else:
                fallback_timeout = max(20.0, min(120.0, parse_timeout_sec))
                fallback_input_bytes = parse_input_bytes
                fallback_input_name = parse_input_name
                fallback_track = "VisualTrack->FastTrackTimeoutFallback"
                fallback_hint = "pdf_visual_timeout_fallback_fasttrack"
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
                        fallback_input_bytes,
                        fallback_input_name,
                        "FastTrack",
                    ),
                    timeout=fallback_timeout,
                )
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
                parse_track = fallback_track
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
    _emit_progress("parsed", 0.64, "版面解析完成，正在抽取字段与图表")

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
    _emit_progress("extracting", 0.72, "正在抽取字段、表格、图片与溯源信息")
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
    _emit_progress("finalizing", 0.92, "抽取完成，正在整理结果与缓存")
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
    soft_warnings = _strip_recovered_extract_warnings(
        soft_warnings,
        quality_ok=not degraded_reasons,
        quick_fallback=used_quick_fallback,
    )
    soft_warnings = _normalize_soft_warnings(soft_warnings)

    if parse_input_name.lower().endswith(".pdf"):
        try:
            pdf_preview_frag, pdf_preview_url = _write_artifact_bytes(
                data=parse_input_bytes,
                file_name=f"{Path(file_name).stem}.pdf",
                sub_dir="preview/pdf",
                ext=".pdf",
            )
            conversion_diag.setdefault("pdf_preview_path", pdf_preview_frag)
            conversion_diag.setdefault("pdf_preview_url", pdf_preview_url)
        except Exception as exc:
            soft_warnings.append(f"pdf_preview_cache_failed:{type(exc).__name__}")
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
        "word_pdf_required": bool(word_parse_via_pdf) if is_word_file(file_name) else False,
        "word_parse_via_pdf": bool(word_parse_via_pdf) if is_word_file(file_name) else False,
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

    if table_blocks or figure_blocks:
        artifact_path, artifact_url = _persist_assistant_payload_artifact(
            file_name=file_name,
            file_hash=decision.file_hash,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
        )
        if artifact_path:
            diagnostics["assistant_payload_artifact_path"] = artifact_path
            diagnostics["assistant_payload_artifact_url"] = artifact_url
            diagnostics["assistant_payload_version"] = "module2-assistant-payload-v1"

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

    _emit_progress("completed", 1.0, "抽取完成")

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


async def _read_upload_file_bytes(file: UploadFile) -> Tuple[str, bytes]:
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
    return file_name, file_bytes


async def _run_extraction_job(
    *,
    job_id: str,
    loaded_files: List[Tuple[str, bytes, str, str, str, str]],
    schema_obj: Dict[str, Any],
    schema_digest: str,
    max_retries: int,
    tenant_id: str,
    request: Request,
) -> None:
    async with extraction_lock:
        job = extraction_jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = time.time()

    for file_index, (file_name, file_bytes, file_hash, artifact_path, artifact_url, _mime_type) in enumerate(
        loaded_files,
        start=1,
    ):
        def _update_progress(stage: str, ratio: float, message: str, extra: Dict[str, Any]) -> None:
            async def _mutate() -> None:
                async with extraction_lock:
                    job_state = extraction_jobs.get(job_id)
                    if not job_state:
                        return
                    job_state.updated_at = time.time()
                    if 0 <= (file_index - 1) < len(job_state.files):
                        file_state = job_state.files[file_index - 1]
                        # Do not mark a file as completed from progress callbacks alone.
                        # The final completion state is only trustworthy after the document
                        # has been appended and the job counters have been updated.
                        next_status = "running"
                        if stage == "queued":
                            next_status = "queued"
                        elif stage == "failed":
                            next_status = "failed"
                        if not (file_state.status in {"completed", "failed"} and next_status not in {"completed", "failed"}):
                            job_state.current_file_index = file_index
                            job_state.current_file_name = file_name
                            job_state.current_stage = stage
                            file_state.status = next_status
                            file_state.stage = stage
                            file_state.progress_ratio = max(0.0, min(1.0, float(ratio)))
                            file_state.message = message or file_state.message

            task = asyncio.create_task(_mutate())
            task.add_done_callback(lambda _: None)

        _update_progress("queued", 0.0, "已进入解析队列", {})
        try:
            doc = await _process_single_doc_bytes(
                file_name=file_name,
                file_bytes=file_bytes,
                schema=schema_obj,
                schema_hash=schema_digest,
                max_retries=max_retries,
                progress_hook=_update_progress,
            )
            async with extraction_lock:
                job_state = extraction_jobs.get(job_id)
                if not job_state:
                    return
                if 0 <= (file_index - 1) < len(job_state.files):
                    file_state = job_state.files[file_index - 1]
                    file_state.progress_ratio = 1.0
                    file_state.status = "failed" if doc.errors else "completed"
                    file_state.stage = "completed" if not doc.errors else "failed"
                    file_state.message = "抽取完成" if not doc.errors else "抽取完成，但存在错误"
                    file_state.track = doc.track
                    file_state.cached = bool(doc.cached)
                    if doc.errors:
                        file_state.error = " | ".join(doc.errors)
                job_state.documents.append(doc)
                if doc.errors:
                    job_state.failed_files += 1
                    job_state.errors.append(f"{file_name}: {' | '.join(doc.errors)}")
                else:
                    job_state.completed_files += 1
                job_state.current_file_index = file_index
                job_state.current_file_name = file_name
                job_state.current_stage = "completed"
                job_state.updated_at = time.time()
        except Exception as exc:
            async with extraction_lock:
                job_state = extraction_jobs.get(job_id)
                if not job_state:
                    return
                if 0 <= (file_index - 1) < len(job_state.files):
                    file_state = job_state.files[file_index - 1]
                    file_state.progress_ratio = 1.0
                    file_state.status = "failed"
                    file_state.stage = "failed"
                    file_state.error = f"{type(exc).__name__}: {exc}"
                    file_state.message = "抽取失败"
                job_state.failed_files += 1
                job_state.errors.append(f"{file_name}: {type(exc).__name__}: {exc}")
                job_state.current_file_index = file_index
                job_state.current_file_name = file_name
                job_state.current_stage = "failed"
                job_state.updated_at = time.time()

    async with extraction_lock:
        job = extraction_jobs.get(job_id)
        if not job:
            return
        done = int(job.completed_files + job.failed_files)
        if done < int(job.total_files):
            job.status = "running"
        elif job.completed_files == 0:
            job.status = "failed"
        else:
            job.status = "completed"
        job.current_stage = "completed" if job.status == "completed" else ("failed" if job.status == "failed" else job.current_stage)
        job.updated_at = time.time()


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


@app.post("/extract/jobs/create")
async def extract_jobs_create(
    request: Request,
    files: List[UploadFile] = File(...),
    schema: str = Form(...),
    tenant_id: str = Form(default=""),
) -> Dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    schema_obj = _parse_schema_form_json(schema)

    loaded_files: List[Tuple[str, bytes, str, str, str, str]] = []
    for file in files:
        file_name, file_bytes = await _read_upload_file_bytes(file)
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = Path(file_name).suffix or ".bin"
        artifact_path, artifact_url = _write_artifact_bytes(
            data=file_bytes,
            file_name=file_name,
            sub_dir="preview/uploaded",
            ext=ext,
        )
        mime_type = (file.content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream").strip()
        loaded_files.append((file_name, file_bytes, file_hash, artifact_path, artifact_url, mime_type))

    schema_digest = _schema_hash(schema_obj)
    max_retries = max(0, min(int(os.getenv("MODULE2_MAX_RETRIES", "2")), 6))
    job_id = f"extract_job_{uuid.uuid4().hex[:16]}"
    now_ts = time.time()
    job_state = ExtractionJobState(
        job_id=job_id,
        status="queued",
        created_at=now_ts,
        updated_at=now_ts,
        total_files=len(loaded_files),
        completed_files=0,
        failed_files=0,
        current_file_index=0,
        current_file_name="",
        current_stage="queued",
        files=[
            ExtractionJobFileState(
                file_name=file_name,
                file_hash=file_hash,
                status="queued",
                stage="queued",
                progress_ratio=0.0,
                message="等待开始解析",
                artifact_path=artifact_path,
                artifact_url=artifact_url,
            )
            for file_name, _, file_hash, artifact_path, artifact_url, _mime_type in loaded_files
        ],
        documents=[],
        errors=[],
    )

    async with extraction_lock:
        _cleanup_extraction_jobs_locked()
        extraction_jobs[job_id] = job_state

    resolved_tenant = _module4_tenant(request, tenant_id)
    upload_payload = [
        {
            "file_name": file_name,
            "file_hash": file_hash,
            "artifact_path": artifact_path,
            "artifact_url": artifact_url,
            "storage_path": _absolute_artifact_storage_path(artifact_path),
            "mime_type": mime_type,
            "metadata": {
                "source_job_id": job_id,
                "artifact_fragment": artifact_path,
            },
        }
        for file_name, _file_bytes, file_hash, artifact_path, artifact_url, mime_type in loaded_files
    ]
    upload_batch_key = _module4_upload_source_batch_key(
        source="module2",
        tenant_id=resolved_tenant,
        uploads=upload_payload,
        seed=f"extract_job_upload:{schema_digest}:{job_id}",
    )
    _spawn_module4_upload_sync_task(
        source="module2",
        tenant_id=resolved_tenant,
        uploads=upload_payload,
        source_batch_key=upload_batch_key,
    )

    asyncio.create_task(
        _run_extraction_job(
            job_id=job_id,
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=tenant_id,
            request=request,
        )
    )

    return _serialize_extraction_job(job_state, include_documents=False)


@app.get("/extract/jobs/status/{job_id}")
async def extract_jobs_status(job_id: str, include_documents: bool = False) -> Dict[str, Any]:
    async with extraction_lock:
        _cleanup_extraction_jobs_locked()
        job = extraction_jobs.get(str(job_id).strip())
        if not job:
            raise HTTPException(status_code=404, detail="Extraction job not found")
        return _serialize_extraction_job(job, include_documents=include_documents)


@app.post("/extract/batch", response_model=BatchExtractionResponse)
async def extract_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    schema: str = Form(...),
    tenant_id: str = Form(default=""),
) -> BatchExtractionResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    if len(files) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    schema_obj = _parse_schema_form_json(schema)

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

    resolved_tenant = _module4_tenant(request, tenant_id)
    source_batch_key = _module4_source_batch_key(
        source="module2",
        tenant_id=resolved_tenant,
        documents=results,
        seed=f"extract_batch:{schema_digest}",
    )
    _spawn_module4_sync_task(
        source="module2",
        tenant_id=resolved_tenant,
        documents=results,
        source_batch_key=source_batch_key,
    )
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
            if existing.file_hash != file_hash:
                continue
            if existing.status in {"queued", "running"}:
                return _serialize_office_preview_job(existing)
            if existing.status == "completed" and existing.artifact_url:
                if _office_preview_artifact_exists(existing):
                    return _serialize_office_preview_job(existing)
                existing.status = "failed"
                existing.updated_at = time.time()
                existing.artifact_path = None
                existing.artifact_url = None
                existing.error = "stale_preview_artifact_missing"
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
    tenant_id: str,
    request_id: str,
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

    sync_documents: List[DocumentExtractionResponse] = []
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
            sync_documents = list(job.documents)
        job.updated_at = time.time()

    if sync_documents:
        source_batch_key = _module4_source_batch_key(
            source="module2",
            tenant_id=tenant_id,
            documents=sync_documents,
            seed=f"dify_bridge:{request_id}:{schema_hash}",
        )
        _spawn_module4_sync_task(
            source="module2",
            tenant_id=tenant_id,
            documents=sync_documents,
            source_batch_key=source_batch_key,
        )


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
    resolved_tenant = _module4_tenant(request, payload.tenant_id or "")

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
            tenant_id=resolved_tenant,
            request_id=request_id,
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


@app.post("/extract/assistant/session", response_model=AssistantSessionResponse)
async def extract_assistant_session(payload: AssistantSessionRequest) -> AssistantSessionResponse:
    return await assistant_service.ensure_session(payload)


@app.post("/extract/assistant/chat/stream")
async def extract_assistant_chat_stream(payload: AssistantChatStreamRequest) -> StreamingResponse:
    return StreamingResponse(
        assistant_service.stream_chat(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/extract/cache/clear", response_model=CacheClearResponse)
async def extract_cache_clear() -> CacheClearResponse:
    cache_counts = await storage.clear_runtime_cache()
    removed_artifacts = _clear_artifact_cache_dir()
    async with office_preview_lock:
        office_preview_jobs.clear()
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
    return FileResponse(
        path=target,
        media_type=media_type,
        filename=target.name,
        content_disposition_type="inline",
    )


@app.api_route("/extract/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
async def extract_artifact(artifact_path: str, request: Request) -> Response:
    target = _safe_artifact_path(artifact_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_path}")
    if request.method.upper() == "HEAD":
        return _head_response_for_file(target)
    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(
        path=target,
        media_type=media_type,
        filename=target.name,
        content_disposition_type="inline",
    )


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {
        "status": "ok",
        "bridge_jobs_in_memory": str(len(bridge_jobs)),
        "bridge_request_index_size": str(len(bridge_request_index)),
        "office_preview_jobs_in_memory": str(len(office_preview_jobs)),
        "module4_sync_enabled": str(_module4_sync_enabled()).lower(),
        "module4_sync_inflight_batches": str(len(module4_sync_tasks)),
        "module4_sync_attempted_batches": str(module4_sync_metrics.get("attempted_batches", 0)),
        "module4_sync_succeeded_batches": str(module4_sync_metrics.get("succeeded_batches", 0)),
        "module4_sync_failed_batches": str(module4_sync_metrics.get("failed_batches", 0)),
        "module4_sync_last_error": str(module4_sync_metrics.get("last_error", "") or ""),
        "module4_sync_last_job_id": str(module4_sync_metrics.get("last_job_id", "") or ""),
        "module4_sync_last_batch_id": str(module4_sync_metrics.get("last_batch_id", "") or ""),
        "module4_sync_last_endpoint": str(module4_sync_metrics.get("last_endpoint", "") or ""),
        "module4_sync_last_source_batch_key": str(module4_sync_metrics.get("last_source_batch_key", "") or ""),
        "bridge_token_required": str(_bridge_token_required()).lower(),
        "bridge_remote_allow_http": str(_bridge_allow_http_remote()).lower(),
        "storage_db_connected": str(storage.diagnostics().get("db_connected", False)).lower(),
        "storage_degraded_memory_mode": str(storage.diagnostics().get("degraded_memory_mode", False)).lower(),
    }

