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
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

MODULE2_ROOT = Path(__file__).resolve().parents[1]

# Always load Module 2's own env file so uvicorn startup from repo root
# does not silently miss the module-specific LLM/timeout settings.
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.assistant.provider import build_module2_llm_provider
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
module4_sync_task_index: Dict[str, asyncio.Task[Any]] = {}
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
provider_preflight_lock = Lock()
provider_preflight_state: Dict[str, Any] = {
    "ok": False,
    "checked_at": 0.0,
    "base_url": "",
    "model": "",
    "error": "",
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
    converter: str = ""
    elapsed_ms: int = 0


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


_EXTRACTION_PROGRESS_STAGE_META: Dict[str, Dict[str, float]] = {
    "queued": {"ceiling": 0.06, "ramp_sec": 8.0, "max_headroom": 0.06},
    "preflight": {"ceiling": 0.12, "ramp_sec": 4.0, "max_headroom": 0.06},
    "converting": {"ceiling": 0.28, "ramp_sec": 16.0, "max_headroom": 0.12},
    "parsing": {"ceiling": 0.74, "ramp_sec": 24.0, "max_headroom": 0.22},
    "parsed": {"ceiling": 0.78, "ramp_sec": 5.0, "max_headroom": 0.08},
    "extracting": {"ceiling": 0.93, "ramp_sec": 28.0, "max_headroom": 0.18},
    "finalizing": {"ceiling": 0.98, "ramp_sec": 12.0, "max_headroom": 0.08},
}


def _normalize_extraction_stage_name(stage: Any) -> str:
    return str(stage or "").strip().lower() or "queued"


def _ease_out_cubic(value: float) -> float:
    t = max(0.0, min(1.0, float(value or 0.0)))
    return 1.0 - pow(1.0 - t, 3)


def _heartbeat_progress_ratio(
    *,
    base_ratio: float,
    stage: Any,
    elapsed_sec: float,
    ceiling_ratio: Optional[float] = None,
    ramp_sec: Optional[float] = None,
) -> float:
    stage_name = _normalize_extraction_stage_name(stage)
    meta = _EXTRACTION_PROGRESS_STAGE_META.get(stage_name, {})
    base = max(0.0, min(1.0, float(base_ratio or 0.0)))
    resolved_ceiling = max(
        base,
        min(
            1.0,
            float(
                ceiling_ratio
                if ceiling_ratio is not None
                else meta.get("ceiling", min(0.96, base + 0.12))
            ),
        ),
    )
    if resolved_ceiling <= base:
        return base
    resolved_ramp = max(2.0, float(ramp_sec if ramp_sec is not None else meta.get("ramp_sec", 10.0)))
    return base + (resolved_ceiling - base) * _ease_out_cubic(elapsed_sec / resolved_ramp)


def _resolve_parse_progress_ramp_sec(*, parse_input_bytes_len: int, timeout_sec: float) -> float:
    size_mb = max(0.0, float(parse_input_bytes_len) / (1024.0 * 1024.0))
    size_driven = 24.0 + min(36.0, size_mb * 9.0)
    timeout_driven = max(30.0, max(0.0, float(timeout_sec)) * 0.55)
    return min(110.0, max(size_driven, timeout_driven))


def _resolve_extract_progress_ramp_sec(
    *,
    timeout_sec: float,
    schema_field_count: int,
    table_count: int,
    figure_count: int,
) -> float:
    complexity = (
        max(0.0, min(float(schema_field_count), 24.0)) * 0.7
        + max(0.0, min(float(table_count), 24.0)) * 0.4
        + max(0.0, min(float(figure_count), 120.0)) * 0.08
    )
    complexity_driven = 22.0 + min(28.0, complexity * 1.15)
    timeout_driven = max(24.0, max(0.0, float(timeout_sec)) * 0.42)
    return min(96.0, max(complexity_driven, timeout_driven))


async def _run_with_progress_heartbeat(
    awaitable: Awaitable[Any],
    *,
    emit_progress: Callable[[str, float, str, Optional[Dict[str, Any]]], Awaitable[None]],
    stage: str,
    base_ratio: float,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
    ceiling_ratio: Optional[float] = None,
    ramp_sec: Optional[float] = None,
    interval_sec: Optional[float] = None,
) -> Any:
    stage_name = _normalize_extraction_stage_name(stage)
    tick_interval_sec = max(0.35, float(interval_sec or os.getenv("MODULE2_PROGRESS_HEARTBEAT_INTERVAL_SEC", "0.8")))
    started_at = time.perf_counter()
    stop_event = asyncio.Event()

    async def _heartbeat() -> None:
        try:
            while True:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=tick_interval_sec)
                    return
                except TimeoutError:
                    pass
                ratio = _heartbeat_progress_ratio(
                    base_ratio=base_ratio,
                    stage=stage_name,
                    elapsed_sec=max(0.0, time.perf_counter() - started_at),
                    ceiling_ratio=ceiling_ratio,
                    ramp_sec=ramp_sec,
                )
                if ratio > base_ratio:
                    await emit_progress(stage_name, ratio, message, extra)
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        return await awaitable
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


EXTRACTION_CACHE_VERSION = (
    str(os.getenv("MODULE2_EXTRACTION_CACHE_VERSION", "20260318-strict-visual-chain-v1")).strip()
    or "20260318-strict-visual-chain-v1"
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


def _build_process_pool() -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=_max_workers())


process_pool = _build_process_pool()
process_pool_lock = Lock()
process_pool_generation = 0


def _shutdown_process_pool(pool: ProcessPoolExecutor, *, reason: str) -> None:
    processes = getattr(pool, "_processes", None)
    if isinstance(processes, dict):
        for proc in list(processes.values()):
            if proc is None:
                continue
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                continue
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        logger.warning("module2 process pool shutdown failed (%s): %s: %s", reason, type(exc).__name__, exc)


def _current_process_pool() -> ProcessPoolExecutor:
    with process_pool_lock:
        return process_pool


def _reset_process_pool(reason: str) -> int:
    global process_pool, process_pool_generation
    with process_pool_lock:
        old_pool = process_pool
        process_pool = _build_process_pool()
        process_pool_generation += 1
        generation = process_pool_generation
    _shutdown_process_pool(old_pool, reason=reason)
    logger.warning("module2 process pool reset to generation=%s due to %s", generation, reason)
    return generation


async def _run_parse_in_process_pool(
    *,
    loop: asyncio.AbstractEventLoop,
    file_bytes: bytes,
    file_name: str,
    track: str,
    timeout_sec: float,
    context_label: str,
    source_file_name: Optional[str] = None,
    source_file_bytes: Optional[bytes] = None,
) -> Any:
    executor = _current_process_pool()
    future = loop.run_in_executor(
        executor,
        parse_document_in_subprocess,
        file_bytes,
        file_name,
        track,
        source_file_name,
        source_file_bytes,
    )
    try:
        return await asyncio.wait_for(future, timeout=timeout_sec)
    except TimeoutError:
        _reset_process_pool(f"parse_timeout:{context_label}")
        raise
    except BrokenProcessPool:
        _reset_process_pool(f"broken_process_pool:{context_label}")
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "process pool" in message or "multiprocessing" in message:
            _reset_process_pool(f"process_pool_error:{context_label}")
        raise

app = FastAPI(title="A23 Module 2 - Unstructured Document Extraction", version="1.0.0")
CORS_ORIGINS, CORS_ALLOW_ALL = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = ExtractionStorage(os.getenv("MODULE2_DATABASE_DSN", "postgresql://postgres@127.0.0.1:5432/a23"))
graph = ExtractionGraph()
assistant_service = AssistantService(storage)
bridge_jobs: Dict[str, BridgeJobState] = {}
bridge_request_index: Dict[str, str] = {}
bridge_lock = asyncio.Lock()
office_preview_jobs: Dict[str, OfficePreviewJob] = {}
office_preview_lock = asyncio.Lock()
extraction_jobs: Dict[str, ExtractionJobState] = {}
extraction_lock = asyncio.Lock()
extraction_job_runtime_specs: Dict[str, Dict[str, Any]] = {}
extraction_job_tasks: Dict[str, asyncio.Task[Any]] = {}
extraction_job_persist_markers: Dict[str, float] = {}


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


_AUTO_SCHEMA_STOPWORDS_EN = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "to",
    "was",
    "were",
    "with",
}

_AUTO_SCHEMA_GENERIC_EN = {
    "appendix",
    "chapter",
    "content",
    "contents",
    "data",
    "equation",
    "eqn",
    "exercise",
    "figure",
    "fig",
    "index",
    "item",
    "items",
    "label",
    "labels",
    "legend",
    "number",
    "page",
    "part",
    "ratio",
    "rate",
    "score",
    "section",
    "series",
    "sheet",
    "system",
    "table",
    "text",
    "value",
    "xaxis",
    "yaxis",
}

_AUTO_SCHEMA_GENERIC_ZH = {
    "字段",
    "内容",
    "序号",
    "备注",
    "说明",
    "项目",
    "数据",
    "文本",
    "页码",
    "图",
    "图片",
    "表",
    "表格",
    "图例",
    "横轴",
    "纵轴",
    "坐标轴",
    "其中",
}

_AUTO_SCHEMA_GENERIC_ZH_EXACT = {
    "\u5408\u8ba1",
    "\u5206\u7c7b",
    "\u6ce8\u91ca",
    "\u57ce\u5e02",
    "\u5355\u4f4d",
    "\u5e8a\u4f4d",
    "\u540d\u79f0",
    "\u56fe\u4f8b",
    "\u673a\u6784",
    "\u519c\u6751",
    "\u5750\u6807\u8f74",
    "\u603b\u8ba1",
    "\u6307\u6807",
    "\u6570\u636e",
    "\u6570\u91cf",
    "\u6587\u672c",
    "\u6a2a\u8f74",
    "\u7c7b\u578b",
    "\u7eb5\u8f74",
    "\u7edf\u8ba1",
    "\u7ed3\u679c",
    "\u8bf4\u660e",
    "\u9879\u76ee",
}

_AUTO_SCHEMA_GENERIC_ZH_UNIT_TOKENS = {
    "\u4eba",
    "\u4e2a",
    "\u4e07\u5143",
    "\u4e07\u5f20",
    "\u5bb6",
    "\u5f20",
    "\u5e74",
    "\u5bf9",
    "\u6b21",
    "\u9879",
}

_AUTO_SCHEMA_GENERIC_JA_EXACT = {
    "施設名",
    "設備名",
    "装置名",
    "抽出装置",
    "工程名",
    "指標名",
    "評価対象",
    "対象工程",
    "対象核種",
    "核種",
    "製品種別",
    "実績値",
    "設計値",
}


def _field_name_word_tokens(text: Any) -> List[str]:
    return re.findall(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+", str(text or ""))


def _schema_field_dedup_key(field_name: Any) -> str:
    key = _sanitize_field_name(field_name)
    if not key:
        return ""
    normalized = re.sub(r"_+", "_", key).strip(" _")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower()


def _schema_field_name_sort_key(field_name: Any) -> Tuple[int, int, int, str]:
    key = _sanitize_field_name(field_name)
    if not key:
        return (9, 9, 999, "")
    return (
        1 if key.endswith("_") else 0,
        key.count("_"),
        len(key),
        key.lower(),
    )


def _upsert_schema_field_candidate(
    out: Dict[str, str],
    raw_name: Any,
    type_hint: Any,
    *,
    skip_low_value: bool,
) -> None:
    key = _sanitize_field_name(raw_name)
    if not key:
        return
    if skip_low_value and _is_low_value_auto_schema_field_name(key):
        return

    dedup_key = _schema_field_dedup_key(key)
    if not dedup_key:
        return

    normalized_type = _coerce_field_type(type_hint)
    existing_name = ""
    for current_name in list(out.keys()):
        if _schema_field_dedup_key(current_name) == dedup_key:
            existing_name = current_name
            break

    if not existing_name:
        out[key] = normalized_type
        return

    chosen_name = existing_name
    if _schema_field_name_sort_key(key) < _schema_field_name_sort_key(existing_name):
        chosen_name = key

    merged_type = out.get(existing_name, "string")
    if _schema_field_type_priority(normalized_type) > _schema_field_type_priority(merged_type):
        merged_type = normalized_type

    if chosen_name != existing_name:
        out.pop(existing_name, None)
    out[chosen_name] = merged_type


def _is_low_value_auto_schema_field_name(field_name: Any) -> bool:
    key = _sanitize_field_name(field_name)
    if not key:
        return True
    if key in _AUTO_SCHEMA_GENERIC_ZH:
        return True
    if key in _AUTO_SCHEMA_GENERIC_ZH_EXACT:
        return True
    if key in _AUTO_SCHEMA_GENERIC_JA_EXACT:
        return True

    lower_key = key.lower().strip()
    if not lower_key:
        return True
    if re.fullmatch(r"\d+(?:\s+\d+)*", lower_key):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{2,32}(?:[_ ]\d+(?:\.\d+)?)", key):
        return True
    if re.fullmatch(r"(?:fig(?:ure)?|eqn|equation|table|appendix|chapter|section|exercise)\s*[A-Za-z0-9. ]*", lower_key):
        return True
    if re.fullmatch(r"[A-Za-z]{1,4}\s+[A-Za-z]?\d+(?:\.\d+)?", key):
        return True

    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", key))
    tokens = _field_name_word_tokens(key)
    if not tokens:
        return True
    cjk_tokens = [tok for tok in tokens if re.search(r"[\u4e00-\u9fff]", tok)]
    if cjk_tokens and all(
        tok in _AUTO_SCHEMA_GENERIC_ZH
        or tok in _AUTO_SCHEMA_GENERIC_ZH_EXACT
        or tok in _AUTO_SCHEMA_GENERIC_JA_EXACT
        or tok in _AUTO_SCHEMA_GENERIC_ZH_UNIT_TOKENS
        for tok in cjk_tokens
    ):
        return True

    raw_alpha_tokens = re.findall(r"[A-Za-z]+", key)
    alpha_tokens = [tok.lower() for tok in raw_alpha_tokens]
    if alpha_tokens and all(tok in _AUTO_SCHEMA_STOPWORDS_EN for tok in alpha_tokens):
        return True

    informative_alpha: List[str] = []
    for raw_tok, tok in zip(raw_alpha_tokens, alpha_tokens):
        if tok in _AUTO_SCHEMA_STOPWORDS_EN or tok in _AUTO_SCHEMA_GENERIC_EN:
            continue
        if len(tok) >= 3 or raw_tok.isupper():
            informative_alpha.append(tok)

    if not has_cjk:
        if not informative_alpha and alpha_tokens:
            return True
        if len(alpha_tokens) == 1 and alpha_tokens[0] in _AUTO_SCHEMA_GENERIC_EN:
            return True
        if any(tok.isdigit() for tok in tokens) and len(informative_alpha) <= 1 and len(tokens) <= 3:
            return True
        if len(tokens) <= 3 and any(tok in {"eqn", "fig", "figure", "table"} for tok in alpha_tokens):
            return True

    return False


def _filter_auto_schema_fields(fields: Dict[str, Any], max_fields: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, type_hint in fields.items():
        _upsert_schema_field_candidate(out, name, type_hint, skip_low_value=True)
        if len(out) >= max_fields:
            break
    pruned, _ = _prune_shadowed_auto_schema_fields(out)
    return dict(list(pruned.items())[:max_fields])


def _should_prune_shadowed_auto_field_name(short_name: str, long_name: str) -> bool:
    short_key = _sanitize_field_name(short_name)
    long_key = _sanitize_field_name(long_name)
    if not short_key or not long_key or short_key == long_key:
        return False
    if len(long_key) <= len(short_key) + 1:
        return False

    shadow_roots = [short_key]
    if "_" in short_key:
        prefix = _sanitize_field_name(short_key.split("_", 1)[0])
        if prefix and prefix not in shadow_roots:
            shadow_roots.append(prefix)

    short_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", short_key))
    long_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", long_key))
    if short_has_cjk and long_has_cjk:
        if len(short_key) > 8:
            return False
        return any(root and len(root) <= 4 and root in long_key for root in shadow_roots)

    short_alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", short_key)]
    long_alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", long_key)]
    if short_alpha_tokens and long_alpha_tokens:
        if len(short_alpha_tokens) > 2 or len(short_key) > 12:
            return False
        return any(root.lower() in long_key.lower() for root in shadow_roots) and len(long_alpha_tokens) > len(short_alpha_tokens)

    return False


def _prune_shadowed_auto_schema_fields(
    fields: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    kept = dict(fields)
    removed: Dict[str, str] = {}
    ordered_keys = list(kept.keys())
    longer_keys = sorted(ordered_keys, key=lambda item: (-len(item), item))
    for short_key in ordered_keys:
        if short_key not in kept:
            continue
        for long_key in longer_keys:
            if long_key not in kept or long_key == short_key:
                continue
            if not _should_prune_shadowed_auto_field_name(short_key, long_key):
                continue
            removed[short_key] = f"shadowed_by_more_specific_field:{long_key}"
            kept.pop(short_key, None)
            break
    return kept, removed


def _is_low_value_quick_fallback_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return False

    text = str(value).strip()
    if not text:
        return True
    if _to_number_or_none(text) is not None:
        return False

    lower_text = re.sub(r"\s+", " ", text).strip().lower()
    if len(lower_text) <= 2 and not re.search(r"[\u4e00-\u9fff]", lower_text):
        return True
    if lower_text in _AUTO_SCHEMA_STOPWORDS_EN:
        return True
    if re.match(r"^[\(\[]?(?:fig(?:ure)?|eqn|equation|table)\b", lower_text):
        return True

    alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", lower_text)]
    if alpha_tokens and all(tok in _AUTO_SCHEMA_STOPWORDS_EN for tok in alpha_tokens):
        return True
    return False


_LOW_VALUE_RESULT_GENERIC_EN = _AUTO_SCHEMA_GENERIC_EN | {
    "extract",
    "extracted",
    "generic",
    "metric",
    "output",
    "result",
    "results",
    "summary",
    "unknown",
}

_LOW_VALUE_RESULT_GENERIC_ZH = _AUTO_SCHEMA_GENERIC_ZH | _AUTO_SCHEMA_GENERIC_ZH_EXACT | {
    "鍏朵粬",
    "鍒嗙被",
    "鏍囩",
    "鍚嶇О",
    "绫诲瀷",
    "缁撴灉",
    "缁熻",
    "鎸囨爣",
    "鎽樿",
}


def _normalize_semantic_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\s_:/\\\-|()\[\]{}<>]+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff.%]+", "", text)
    return text


def _is_low_value_result_value(field_name: Any, value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return False

    text = str(value).strip()
    if not text:
        return True
    if _to_number_or_none(text) is not None:
        return False

    normalized_value = _normalize_semantic_text(text)
    normalized_field = _normalize_semantic_text(_sanitize_field_name(field_name))
    if not normalized_value:
        return True
    if normalized_field and normalized_value == normalized_field:
        return True
    if normalized_value in _LOW_VALUE_RESULT_GENERIC_EN or normalized_value in _LOW_VALUE_RESULT_GENERIC_ZH:
        return True
    if normalized_value.startswith(("legend", "xaxis", "yaxis", "xaxislabel", "yaxislabel")):
        return True
    if normalized_value.startswith(
        (
            "\u56fe\u4f8b",
            "\u6a2a\u8f74",
            "\u7eb5\u8f74",
            "\u5750\u6807\u8f74",
        )
    ):
        return True

    alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", normalized_value)]
    if alpha_tokens and all(tok in _AUTO_SCHEMA_STOPWORDS_EN or tok in _LOW_VALUE_RESULT_GENERIC_EN for tok in alpha_tokens):
        return True
    if len(normalized_value) <= 2 and not re.search(r"[\u4e00-\u9fff]", normalized_value):
        return True
    return False


def _filter_low_value_auto_results(
    results: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    filtered: Dict[str, Dict[str, Any]] = {}
    removed: Dict[str, str] = {}
    for field_name, entity in results.items():
        key = _sanitize_field_name(field_name)
        if not key:
            removed[str(field_name)] = "empty_field_name"
            continue
        if not isinstance(entity, dict):
            removed[key] = "invalid_entity"
            continue
        if _is_low_value_auto_schema_field_name(key):
            removed[key] = "low_value_field_name"
            continue
        if _is_low_value_result_value(key, entity.get("value")):
            removed[key] = "low_value_result_value"
            continue
        filtered[key] = entity
    pruned, shadowed_removed = _prune_shadowed_auto_results(filtered)
    removed.update(shadowed_removed)
    return pruned, removed


def _effective_quality_schema_fields(
    schema_fields: Dict[str, Any],
    removed_auto_results: Dict[str, str],
) -> Dict[str, Any]:
    if not schema_fields:
        return {}
    if not removed_auto_results:
        return dict(schema_fields)

    adjusted: Dict[str, Any] = {}
    for field_name, field_type in schema_fields.items():
        sanitized_name = _sanitize_field_name(field_name)
        removal_reason = removed_auto_results.get(sanitized_name) or removed_auto_results.get(str(field_name))
        if removal_reason in {"empty_field_name", "low_value_field_name"}:
            continue
        if str(removal_reason or "").startswith("shadowed_by_more_specific_field:"):
            continue
        adjusted[str(field_name)] = field_type
    return adjusted


def _prune_shadowed_auto_results(
    results: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    kept = dict(results)
    removed: Dict[str, str] = {}
    ordered_keys = list(kept.keys())
    longer_keys = sorted(ordered_keys, key=lambda item: (-len(item), item))
    normalized_values = {
        key: _normalize_semantic_text(entity.get("value"))
        for key, entity in kept.items()
        if isinstance(entity, dict)
    }
    for short_key in ordered_keys:
        if short_key not in kept:
            continue
        short_value = normalized_values.get(short_key, "")
        if not short_value:
            continue
        for long_key in longer_keys:
            if long_key not in kept or long_key == short_key:
                continue
            if not _should_prune_shadowed_auto_field_name(short_key, long_key):
                continue
            long_value = normalized_values.get(long_key, "")
            if not long_value or long_value != short_value:
                continue
            removed[short_key] = f"shadowed_by_more_specific_field:{long_key}"
            kept.pop(short_key, None)
            break
    return kept, removed


def _normalize_schema_fields(fields: Dict[str, Any], max_fields: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, type_hint in fields.items():
        _upsert_schema_field_candidate(out, name, type_hint, skip_low_value=False)
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
        if _is_low_value_auto_schema_field_name(key):
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
    return _filter_auto_schema_fields(out, max_fields=max_fields)


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
        _upsert_schema_field_candidate(
            parsed,
            item.get("field_name"),
            item.get("field_type"),
            skip_low_value=True,
        )
        if len(parsed) >= max_fields:
            break
    return _filter_auto_schema_fields(parsed, max_fields=max_fields)


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
            _upsert_schema_field_candidate(
                merged,
                name,
                type_hint,
                skip_low_value=True,
            )
            if len(merged) >= max_fields:
                break
        if len(merged) >= max_fields:
            break
    merged = _filter_auto_schema_fields(merged, max_fields=max_fields)

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
        if _is_low_value_auto_schema_field_name(field_name):
            continue
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
                    elif _is_low_value_quick_fallback_value(text):
                        continue

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


def _source_counts_have_gemini(source_counts: Dict[str, int]) -> bool:
    return any("gemini" in str(source or "").strip().lower() for source in source_counts.keys())


def _source_counts_all_gemini(source_counts: Dict[str, int]) -> bool:
    non_empty = [str(source or "").strip().lower() for source in source_counts.keys() if str(source or "").strip()]
    return bool(non_empty) and all("gemini" in source for source in non_empty)


def _build_visual_chain_contract(
    *,
    file_name: str,
    parse_input_name: str,
    parse_track: str,
    word_parse_via_pdf: bool,
    conversion_diag: Dict[str, Any],
    parse_stats: Dict[str, Any],
    table_blocks: List[Dict[str, Any]],
    figure_blocks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    file_ext = Path(file_name or "").suffix.lower()
    parse_input_is_pdf = str(parse_input_name or "").lower().endswith(".pdf")
    requires_word_pdf = file_ext in {".doc", ".docx"} and bool(word_parse_via_pdf)
    required = bool(_visual_chain_required() and (file_ext == ".pdf" or requires_word_pdf))
    parse_track_text = str(parse_track or "").strip()
    parse_track_lower = parse_track_text.lower()
    pipeline = str(parse_stats.get("pipeline", "") or "").strip().lower()
    chain_status = str(parse_stats.get("chain_status", "") or "").strip().lower()
    artifact_status = str(parse_stats.get("artifact_status", "") or "").strip().lower()
    vision_status = str(parse_stats.get("vision_status", "") or "").strip().lower()
    baseline_artifact_ready = bool(parse_stats.get("visual_baseline_artifact_ready", False))
    mineru_run = parse_stats.get("mineru_run") if isinstance(parse_stats.get("mineru_run"), dict) else {}
    mineru_status = str(mineru_run.get("status", "") or "").strip().lower()
    fallback_reason = str(parse_stats.get("visual_first_fallback_reason", "") or "").strip()
    table_sources = _table_source_counts(table_blocks)
    figure_sources = _figure_source_counts(figure_blocks)
    reasons: List[str] = []

    if requires_word_pdf and not bool(conversion_diag.get("office_pdf_converted")):
        reasons.append("word_pdf_conversion_missing")
    if requires_word_pdf and not parse_input_is_pdf:
        reasons.append("word_parse_input_not_pdf")

    if required:
        if parse_track_text != "VisualTrack":
            reasons.append(f"parse_track_not_visual:{parse_track_text or 'missing'}")
        if "fasttrack" in parse_track_lower:
            reasons.append("fasttrack_fallback_detected")
        if "nativedocxrecovery" in parse_track_lower:
            reasons.append("native_docx_recovery_detected")
        if pipeline != "visual_first":
            reasons.append(f"pipeline_not_visual_first:{pipeline or 'missing'}")
        if mineru_status != "ok":
            reasons.append(f"mineru_status_not_ok:{mineru_status or 'missing'}")
        if chain_status and chain_status != "success":
            reasons.append(f"chain_status_not_success:{chain_status}")
        if not baseline_artifact_ready:
            reasons.append("baseline_artifact_missing")
        if fallback_reason:
            reasons.append(f"visual_first_fallback:{fallback_reason}")

    return {
        "required": required,
        "satisfied": not reasons,
        "reasons": reasons,
        "requires_word_pdf": requires_word_pdf,
        "parse_input_is_pdf": parse_input_is_pdf,
        "parse_track": parse_track_text,
        "pipeline": pipeline,
        "chain_status": chain_status,
        "artifact_status": artifact_status,
        "vision_status": vision_status,
        "baseline_artifact_ready": baseline_artifact_ready,
        "mineru_status": mineru_status,
        "visual_first_fallback_reason": fallback_reason,
        "table_source_counts": table_sources,
        "figure_source_counts": figure_sources,
    }


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
            if candidate.exists() and candidate.is_file():
                digest = hashlib.sha1(str(candidate).encode("utf-8", "ignore")).hexdigest()[:16]
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate.name) or f"artifact{candidate.suffix.lower()}"
                mirror_rel = Path("linked") / digest / safe_name
                mirror_path = (root / mirror_rel).resolve()
                mirror_path.relative_to(root)
                source_stat = candidate.stat()
                should_copy = True
                if mirror_path.exists():
                    try:
                        mirror_stat = mirror_path.stat()
                        should_copy = (
                            mirror_stat.st_size != source_stat.st_size
                            or int(mirror_stat.st_mtime) != int(source_stat.st_mtime)
                        )
                    except Exception:
                        should_copy = True
                if should_copy:
                    mirror_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, mirror_path)
                return str(mirror_rel).replace("\\", "/")
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


def _normalize_content_hash(value: Any) -> str:
    raw = str(value or "").strip().lower()
    compact = re.sub(r"[^a-f0-9]+", "", raw)
    if len(compact) >= 24:
        return compact
    if raw:
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
    return hashlib.sha256(b"module2_office_preview").hexdigest()


def _office_preview_storage_fragments(file_hash: str) -> Tuple[str, str]:
    normalized_hash = _normalize_content_hash(file_hash)
    rel_dir = Path("preview") / "office_pdf" / "by_source" / normalized_hash[:2] / normalized_hash
    pdf_fragment = str((rel_dir / "source.pdf").as_posix())
    meta_fragment = str((rel_dir / "meta.json").as_posix())
    return pdf_fragment, meta_fragment


def _write_office_preview_artifact(
    *,
    file_name: str,
    file_hash: str,
    pdf_bytes: bytes,
    convert_meta: Dict[str, Any],
) -> Tuple[str, str]:
    pdf_fragment, meta_fragment = _office_preview_storage_fragments(file_hash)
    pdf_path = _safe_artifact_path(pdf_fragment)
    meta_path = _safe_artifact_path(meta_fragment)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    payload = {
        "version": "module2-office-preview-v1",
        "file_name": str(file_name or ""),
        "file_hash": _normalize_content_hash(file_hash),
        "artifact_path": pdf_fragment,
        "artifact_url": _artifact_url_from_fragment(pdf_fragment),
        "converter": str(convert_meta.get("converter", "") or ""),
        "elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_size": len(pdf_bytes),
        "updated_at": time.time(),
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pdf_fragment, _artifact_url_from_fragment(pdf_fragment)


def _load_office_preview_record(file_hash: str) -> Dict[str, Any]:
    normalized_hash = _normalize_content_hash(file_hash)
    pdf_fragment, meta_fragment = _office_preview_storage_fragments(normalized_hash)
    pdf_path = _safe_artifact_path(pdf_fragment)
    if not pdf_path.exists() or not pdf_path.is_file():
        return {}
    meta_path = _safe_artifact_path(meta_fragment)
    payload: Dict[str, Any] = {}
    if meta_path.exists() and meta_path.is_file():
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(raw, dict):
                payload = dict(raw)
        except Exception:
            payload = {}
    payload["file_hash"] = normalized_hash
    payload["artifact_path"] = pdf_fragment
    payload["artifact_url"] = _artifact_url_from_fragment(pdf_fragment)
    payload["updated_at"] = float(payload.get("updated_at", pdf_path.stat().st_mtime) or pdf_path.stat().st_mtime)
    payload["file_name"] = str(payload.get("file_name", "") or "")
    payload["converter"] = str(payload.get("converter", "") or "")
    payload["elapsed_ms"] = int(payload.get("elapsed_ms", 0) or 0)
    return payload


def _recover_office_preview_job_from_disk_locked(*, file_hash: str, file_name: str = "") -> Optional[OfficePreviewJob]:
    record = _load_office_preview_record(file_hash)
    if not record:
        return None
    normalized_hash = str(record.get("file_hash") or _normalize_content_hash(file_hash)).strip().lower()
    updated_at = float(record.get("updated_at", time.time()) or time.time())
    recovered = OfficePreviewJob(
        job_id=f"preview_disk_{normalized_hash[:16]}",
        status="completed",
        created_at=updated_at,
        updated_at=updated_at,
        file_name=str(record.get("file_name") or file_name or ""),
        file_hash=normalized_hash,
        artifact_path=str(record.get("artifact_path") or ""),
        artifact_url=str(record.get("artifact_url") or ""),
        error="",
        converter=str(record.get("converter") or "preview_disk_cache"),
        elapsed_ms=int(record.get("elapsed_ms", 0) or 0),
    )
    office_preview_jobs[recovered.job_id] = recovered
    return recovered


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


def _visual_chain_required() -> bool:
    return (os.getenv("MODULE2_REQUIRE_VISUAL_CHAIN", "true") or "true").lower() in {"1", "true", "yes"}


def _provider_healthcheck_on_job_create() -> bool:
    return (os.getenv("MODULE2_PROVIDER_HEALTHCHECK_ON_JOB_CREATE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
    }


def _fail_on_provider_unavailable() -> bool:
    return (os.getenv("MODULE2_FAIL_ON_PROVIDER_UNAVAILABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
    }


def _disable_fasttrack_fallback() -> bool:
    return (os.getenv("MODULE2_DISABLE_FASTTRACK_FALLBACK", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
    }


def _disable_quick_table_fallback() -> bool:
    return (os.getenv("MODULE2_DISABLE_QUICK_TABLE_FALLBACK", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
    }


def _provider_healthcheck_ttl_sec() -> float:
    return max(5.0, float(os.getenv("MODULE2_PROVIDER_HEALTHCHECK_TTL_SEC", "120")))


def _provider_healthcheck_timeout_sec() -> float:
    return max(5.0, float(os.getenv("MODULE2_PROVIDER_HEALTHCHECK_TIMEOUT_SEC", "20")))


def _provider_preflight_snapshot() -> Dict[str, Any]:
    with provider_preflight_lock:
        return dict(provider_preflight_state)


def _run_provider_preflight(force: bool = False) -> Dict[str, Any]:
    ttl_sec = _provider_healthcheck_ttl_sec()
    now_ts = time.time()
    with provider_preflight_lock:
        cached_ok = bool(provider_preflight_state.get("ok"))
        checked_at = float(provider_preflight_state.get("checked_at", 0.0) or 0.0)
        if (not force) and cached_ok and (now_ts - checked_at) < ttl_sec:
            return dict(provider_preflight_state)

    provider = build_module2_llm_provider(
        temperature=0.0,
        max_tokens=8,
        timeout_sec=_provider_healthcheck_timeout_sec(),
    )
    if not provider.configured:
        message = "module2 extraction provider is not fully configured"
        with provider_preflight_lock:
            provider_preflight_state.update(
                {
                    "ok": False,
                    "checked_at": time.time(),
                    "base_url": getattr(provider, "base_url", ""),
                    "model": getattr(provider, "model", ""),
                    "error": message,
                }
            )
        raise RuntimeError(message)

    try:
        result = provider.healthcheck(timeout_sec=_provider_healthcheck_timeout_sec())
    except Exception as exc:
        message = str(exc or "").strip() or f"{type(exc).__name__}"
        with provider_preflight_lock:
            provider_preflight_state.update(
                {
                    "ok": False,
                    "checked_at": time.time(),
                    "base_url": provider.base_url,
                    "model": provider.model,
                    "error": message,
                }
            )
        raise

    with provider_preflight_lock:
        provider_preflight_state.update(
            {
                "ok": True,
                "checked_at": float(result.get("checked_at", time.time()) or time.time()),
                "base_url": str(result.get("base_url", "") or provider.base_url),
                "model": str(result.get("model", "") or provider.model),
                "error": "",
            }
        )
        return dict(provider_preflight_state)


async def _ensure_provider_ready_for_job_create() -> None:
    if not _provider_healthcheck_on_job_create():
        return
    try:
        await asyncio.to_thread(_run_provider_preflight)
    except Exception as exc:
        logger.warning("module2 provider preflight failed: %s: %s", type(exc).__name__, exc)
        if _fail_on_provider_unavailable():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Extraction provider preflight failed before job creation: "
                    f"{type(exc).__name__}: {exc}"
                ),
            ) from exc


def _docx_native_recovery_enabled() -> bool:
    return (os.getenv("MODULE2_DOCX_NATIVE_RECOVERY_ENABLE", "false") or "false").lower() in {
        "1",
        "true",
        "yes",
    }


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


def _office_preview_find_by_hash_locked(file_hash: str, file_name: str = "") -> Optional[OfficePreviewJob]:
    normalized = str(file_hash or "").strip().lower()
    if not normalized:
        return None

    matches = [
        job
        for job in office_preview_jobs.values()
        if str(job.file_hash or "").strip().lower() == normalized
    ]
    completed_matches = [job for job in matches if job.status == "completed" and _office_preview_artifact_exists(job)]
    if completed_matches:
        completed_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
        return completed_matches[0]

    running_matches = [job for job in matches if job.status in {"queued", "running"}]
    if running_matches:
        running_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
        return running_matches[0]

    recovered = _recover_office_preview_job_from_disk_locked(file_hash=normalized, file_name=file_name)
    if recovered is not None:
        return recovered

    if not matches:
        return None
    matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
    return matches[0]


def _read_office_preview_artifact_bytes(job: OfficePreviewJob) -> bytes:
    fragment = _artifact_fragment_from_path(job.artifact_path)
    if not fragment:
        raise FileNotFoundError("office_preview_artifact_missing_fragment")
    target = _safe_artifact_path(fragment)
    return target.read_bytes()


async def _await_or_reuse_office_preview_pdf(
    *,
    file_name: str,
    file_hash: str,
    timeout_sec: float,
) -> Tuple[Optional[bytes], Dict[str, Any]]:
    deadline = time.perf_counter() + max(2.0, float(timeout_sec))
    wait_started = time.perf_counter()
    saw_running = False

    while True:
        async with office_preview_lock:
            _office_preview_cleanup_jobs_locked()
            job = _office_preview_find_by_hash_locked(file_hash, file_name)
            if job is None:
                return None, {}

            if job.status == "completed":
                try:
                    pdf_bytes = _read_office_preview_artifact_bytes(job)
                except Exception as exc:
                    job.status = "failed"
                    job.updated_at = time.time()
                    if not str(job.error or "").strip():
                        job.error = f"artifact_read_failed:{type(exc).__name__}:{exc}"
                    return None, {
                        "office_pdf_preview_error": job.error,
                        "office_pdf_preview_job_id": job.job_id,
                    }
                return pdf_bytes, {
                    "office_pdf_preview_reused": True,
                    "office_pdf_preview_job_id": job.job_id,
                    "artifact_path": job.artifact_path,
                    "artifact_url": job.artifact_url,
                    "converter": str(job.converter or "").strip() or "preview_cache",
                    "elapsed_ms": int(job.elapsed_ms or 0),
                    "waited_ms": int((time.perf_counter() - wait_started) * 1000),
                }

            if job.status == "failed":
                return None, {
                    "office_pdf_preview_error": str(job.error or "").strip() or "office_preview_failed",
                    "office_pdf_preview_job_id": job.job_id,
                }

            saw_running = job.status in {"queued", "running"}

        if time.perf_counter() >= deadline:
            if saw_running:
                raise TimeoutError(f"office_preview_wait_timeout:{file_name}")
            return None, {}
        await asyncio.sleep(0.35)


async def _sync_office_preview_job_success(
    *,
    file_name: str,
    file_hash: str,
    artifact_path: str,
    artifact_url: str,
    convert_meta: Dict[str, Any],
) -> None:
    now = time.time()
    async with office_preview_lock:
        _office_preview_cleanup_jobs_locked()
        job = _office_preview_find_by_hash_locked(file_hash, file_name)
        if job is None:
            job = OfficePreviewJob(
                job_id=f"preview_{uuid.uuid4().hex[:16]}",
                status="completed",
                created_at=now,
                updated_at=now,
                file_name=file_name,
                file_hash=file_hash,
                artifact_path=artifact_path,
                artifact_url=artifact_url,
                error="",
                converter=str(convert_meta.get("converter", "") or ""),
                elapsed_ms=int(convert_meta.get("elapsed_ms", 0) or 0),
            )
            office_preview_jobs[job.job_id] = job
            return

        job.status = "completed"
        job.updated_at = now
        job.file_name = file_name
        job.artifact_path = artifact_path
        job.artifact_url = artifact_url
        job.error = ""
        job.converter = str(convert_meta.get("converter", "") or "")
        job.elapsed_ms = int(convert_meta.get("elapsed_ms", 0) or 0)


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
        "converter": job.converter,
        "elapsed_ms": int(job.elapsed_ms or 0),
        "terminal": job.status in {"completed", "failed"},
    }


async def _ensure_office_preview_job_started(
    *,
    file_name: str,
    file_bytes: bytes,
    file_hash: str,
) -> OfficePreviewJob:
    normalized_hash = str(file_hash or "").strip().lower()
    if not normalized_hash:
        raise ValueError("file_hash is required for office preview job")

    created_job: OfficePreviewJob | None = None
    async with office_preview_lock:
        _office_preview_cleanup_jobs_locked()
        existing = _office_preview_find_by_hash_locked(normalized_hash, file_name)
        if existing is not None:
            if existing.status == "completed" and not _office_preview_artifact_exists(existing):
                existing.status = "failed"
                existing.updated_at = time.time()
                existing.artifact_path = None
                existing.artifact_url = None
                existing.error = "stale_preview_artifact_missing"
            else:
                return existing

        now = time.time()
        created_job = OfficePreviewJob(
            job_id=f"preview_{uuid.uuid4().hex[:16]}",
            status="queued",
            created_at=now,
            updated_at=now,
            file_name=file_name,
            file_hash=normalized_hash,
            artifact_path=None,
            artifact_url=None,
            error="",
        )
        office_preview_jobs[created_job.job_id] = created_job

    if created_job is not None:
        asyncio.create_task(_run_office_preview_job(created_job.job_id, file_name, file_bytes))
        return created_job
    raise RuntimeError("office_preview_job_create_failed")


def _serialize_extraction_job(job: ExtractionJobState, *, include_documents: bool = False) -> Dict[str, Any]:
    total_files = max(1, int(job.total_files or 0))
    serialized_files: List[Dict[str, Any]] = []
    file_progress_values: List[float] = []

    for idx, item in enumerate(job.files):
        raw_ratio = max(0.0, min(1.0, float(item.progress_ratio or 0.0)))
        file_progress_values.append(raw_ratio)
        serialized_files.append(
            {
                "file_name": item.file_name,
                "file_hash": item.file_hash,
                "status": item.status,
                "stage": item.stage,
                "progress_ratio": round(raw_ratio, 4),
                "message": item.message,
                "artifact_path": item.artifact_path,
                "artifact_url": item.artifact_url,
                "error": item.error,
                "track": item.track,
                "cached": bool(item.cached),
            }
        )

    progress_ratio = (sum(file_progress_values) / float(total_files)) if file_progress_values else 0.0
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
        "files": serialized_files,
        "errors": list(job.errors),
    }
    if include_documents or job.terminal():
        payload["documents"] = [doc.model_dump(mode="json") for doc in job.documents]
    return payload


def _extraction_job_state_root_dir() -> Path:
    root = Path(
        os.getenv(
            "MODULE2_EXTRACT_JOB_STATE_DIR",
            "backend/module2/.runlogs/extraction_jobs",
        )
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _extraction_job_state_path(job_id: str) -> Path:
    safe_job_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(job_id or "").strip()) or "extract_job"
    return _extraction_job_state_root_dir() / f"{safe_job_id}.json"


def _write_json_file_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _serialize_extraction_job_runtime_spec(job_id: str) -> Dict[str, Any]:
    spec = extraction_job_runtime_specs.get(str(job_id).strip()) or {}
    loaded_files = []
    for item in spec.get("loaded_files", []):
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file_name") or "").strip()
        file_hash = str(item.get("file_hash") or "").strip()
        artifact_path = str(item.get("artifact_path") or "").strip()
        artifact_url = str(item.get("artifact_url") or "").strip()
        mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
        if not file_name or not file_hash or not artifact_path:
            continue
        loaded_files.append(
            {
                "file_name": file_name,
                "file_hash": file_hash,
                "artifact_path": artifact_path,
                "artifact_url": artifact_url,
                "mime_type": mime_type,
            }
        )
    return {
        "schema": spec.get("schema") if isinstance(spec.get("schema"), dict) else {},
        "schema_digest": str(spec.get("schema_digest") or "").strip(),
        "max_retries": max(0, int(spec.get("max_retries") or 0)),
        "tenant_id": str(spec.get("tenant_id") or "").strip(),
        "loaded_files": loaded_files,
    }


def _normalize_extraction_job_runtime_spec(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
    schema_digest = str(payload.get("schema_digest") or "").strip()
    max_retries = max(0, int(payload.get("max_retries") or 0))
    tenant_id = str(payload.get("tenant_id") or "").strip()
    loaded_files: List[Dict[str, str]] = []
    for item in payload.get("loaded_files", []):
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file_name") or "").strip()
        file_hash = str(item.get("file_hash") or "").strip()
        artifact_path = str(item.get("artifact_path") or "").strip()
        artifact_url = str(item.get("artifact_url") or "").strip()
        mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
        if not file_name or not file_hash or not artifact_path:
            continue
        loaded_files.append(
            {
                "file_name": file_name,
                "file_hash": file_hash,
                "artifact_path": artifact_path,
                "artifact_url": artifact_url,
                "mime_type": mime_type,
            }
        )
    return {
        "schema": schema,
        "schema_digest": schema_digest,
        "max_retries": max_retries,
        "tenant_id": tenant_id,
        "loaded_files": loaded_files,
    }


def _deserialize_extraction_job_file_state(payload: Any) -> Optional[ExtractionJobFileState]:
    if not isinstance(payload, dict):
        return None
    file_name = str(payload.get("file_name") or "").strip()
    file_hash = str(payload.get("file_hash") or "").strip()
    if not file_name or not file_hash:
        return None
    return ExtractionJobFileState(
        file_name=file_name,
        file_hash=file_hash,
        status=str(payload.get("status") or "queued").strip() or "queued",
        stage=str(payload.get("stage") or "queued").strip() or "queued",
        progress_ratio=max(0.0, min(1.0, float(payload.get("progress_ratio") or 0.0))),
        message=str(payload.get("message") or "").strip(),
        artifact_path=str(payload.get("artifact_path") or "").strip() or None,
        artifact_url=str(payload.get("artifact_url") or "").strip() or None,
        error=str(payload.get("error") or "").strip(),
        track=str(payload.get("track") or "").strip(),
        cached=bool(payload.get("cached")),
    )


def _deserialize_extraction_job_state(payload: Any) -> Optional[ExtractionJobState]:
    if not isinstance(payload, dict):
        return None
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        return None
    progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
    file_states = [
        file_state
        for item in (payload.get("files") or [])
        if (file_state := _deserialize_extraction_job_file_state(item)) is not None
    ]
    documents: List[DocumentExtractionResponse] = []
    for item in payload.get("documents") or []:
        try:
            documents.append(DocumentExtractionResponse.model_validate(item))
        except Exception:
            continue
    return ExtractionJobState(
        job_id=job_id,
        status=str(payload.get("status") or "queued").strip() or "queued",
        created_at=float(payload.get("created_at") or time.time()),
        updated_at=float(payload.get("updated_at") or time.time()),
        total_files=max(int(progress.get("total_files") or len(file_states) or 0), len(file_states)),
        completed_files=max(0, int(progress.get("completed_files") or 0)),
        failed_files=max(0, int(progress.get("failed_files") or 0)),
        current_file_index=max(0, int(progress.get("current_file_index") or 0)),
        current_file_name=str(progress.get("current_file_name") or "").strip(),
        current_stage=str(progress.get("current_stage") or "queued").strip() or "queued",
        files=file_states,
        documents=documents,
        errors=[str(item or "").strip() for item in (payload.get("errors") or []) if str(item or "").strip()],
    )


def _build_extraction_job_snapshot_payload(job: ExtractionJobState) -> Dict[str, Any]:
    return {
        "version": 1,
        "saved_at": time.time(),
        "job": _serialize_extraction_job(job, include_documents=True),
        "runtime": _serialize_extraction_job_runtime_spec(job.job_id),
    }


def _load_extraction_job_snapshot_file(job_id: str) -> Optional[Dict[str, Any]]:
    path = _extraction_job_state_path(job_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("module2 failed to read extraction job snapshot job=%s: %s: %s", job_id, type(exc).__name__, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _load_extraction_job_loaded_files(runtime_spec: Dict[str, Any]) -> List[Tuple[str, bytes, str, str, str, str]]:
    loaded_files: List[Tuple[str, bytes, str, str, str, str]] = []
    for item in runtime_spec.get("loaded_files", []):
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file_name") or "").strip()
        file_hash = str(item.get("file_hash") or "").strip()
        artifact_path = str(item.get("artifact_path") or "").strip()
        artifact_url = str(item.get("artifact_url") or "").strip()
        mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
        if not file_name or not file_hash or not artifact_path:
            continue
        file_bytes = _safe_artifact_path(artifact_path).read_bytes()
        loaded_files.append((file_name, file_bytes, file_hash, artifact_path, artifact_url, mime_type))
    return loaded_files


def _drop_extraction_job_runtime(job_id: str, *, remove_snapshot: bool) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    extraction_job_runtime_specs.pop(normalized_job_id, None)
    extraction_job_persist_markers.pop(normalized_job_id, None)
    task = extraction_job_tasks.get(normalized_job_id)
    if task and task.done():
        extraction_job_tasks.pop(normalized_job_id, None)
    if remove_snapshot:
        try:
            _extraction_job_state_path(normalized_job_id).unlink(missing_ok=True)
        except Exception:
            pass


def _extraction_job_persist_interval_sec() -> float:
    return max(0.0, float(os.getenv("MODULE2_EXTRACT_JOB_PERSIST_INTERVAL_SEC", "1.0")))


async def _persist_extraction_job_snapshot(job_id: str, *, force: bool = False) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    now_ts = time.time()
    if not force:
        last_ts = float(extraction_job_persist_markers.get(normalized_job_id) or 0.0)
        if (now_ts - last_ts) < _extraction_job_persist_interval_sec():
            return
    async with extraction_lock:
        job = extraction_jobs.get(normalized_job_id)
        if not job:
            snapshot_payload = None
        else:
            snapshot_payload = _build_extraction_job_snapshot_payload(job)
    if snapshot_payload is None:
        _drop_extraction_job_runtime(normalized_job_id, remove_snapshot=True)
        return
    try:
        _write_json_file_atomic(_extraction_job_state_path(normalized_job_id), snapshot_payload)
        extraction_job_persist_markers[normalized_job_id] = now_ts
    except Exception as exc:
        logger.warning(
            "module2 failed to persist extraction job snapshot job=%s: %s: %s",
            normalized_job_id,
            type(exc).__name__,
            exc,
        )


def _schedule_extraction_job_task(
    *,
    job_id: str,
    loaded_files: List[Tuple[str, bytes, str, str, str, str]],
    schema_obj: Dict[str, Any],
    schema_digest: str,
    max_retries: int,
    tenant_id: str,
) -> bool:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    existing_task = extraction_job_tasks.get(normalized_job_id)
    if existing_task and not existing_task.done():
        return False

    task = asyncio.create_task(
        _run_extraction_job(
            job_id=normalized_job_id,
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=tenant_id,
        )
    )
    extraction_job_tasks[normalized_job_id] = task

    def _cleanup_task(done_task: asyncio.Task[Any]) -> None:
        current = extraction_job_tasks.get(normalized_job_id)
        if current is done_task:
            extraction_job_tasks.pop(normalized_job_id, None)

    task.add_done_callback(_cleanup_task)
    return True


async def _mark_extraction_job_resume_failed(job_id: str, message: str) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    async with extraction_lock:
        job = extraction_jobs.get(normalized_job_id)
        if not job:
            return
        job.status = "failed"
        job.updated_at = time.time()
        job.current_stage = "failed"
        if message and message not in job.errors:
            job.errors.append(message)
        for item in job.files:
            if item.status not in {"completed", "failed"}:
                item.status = "failed"
                item.stage = "failed"
                item.progress_ratio = 1.0
                item.error = message
                item.message = "任务恢复失败"
        job.failed_files = sum(1 for item in job.files if item.status == "failed")
    await _persist_extraction_job_snapshot(normalized_job_id, force=True)


async def _restore_extraction_job_from_snapshot(job_id: str) -> Optional[ExtractionJobState]:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    snapshot = _load_extraction_job_snapshot_file(normalized_job_id)
    if not snapshot:
        return None
    job = _deserialize_extraction_job_state(snapshot.get("job"))
    if not job:
        return None
    runtime_spec = _normalize_extraction_job_runtime_spec(snapshot.get("runtime"))
    async with extraction_lock:
        extraction_jobs[normalized_job_id] = job
        extraction_job_runtime_specs[normalized_job_id] = runtime_spec
    if not job.terminal():
        try:
            loaded_files = _load_extraction_job_loaded_files(runtime_spec)
        except Exception as exc:
            await _mark_extraction_job_resume_failed(
                normalized_job_id,
                f"resume_payload_unavailable: {type(exc).__name__}: {exc}",
            )
        else:
            if not loaded_files:
                await _mark_extraction_job_resume_failed(
                    normalized_job_id,
                    "resume_payload_unavailable: no resumable uploaded files found",
                )
                async with extraction_lock:
                    return extraction_jobs.get(normalized_job_id)
            _schedule_extraction_job_task(
                job_id=normalized_job_id,
                loaded_files=loaded_files,
                schema_obj=runtime_spec.get("schema") if isinstance(runtime_spec.get("schema"), dict) else {},
                schema_digest=str(runtime_spec.get("schema_digest") or "").strip(),
                max_retries=max(0, int(runtime_spec.get("max_retries") or 0)),
                tenant_id=str(runtime_spec.get("tenant_id") or "").strip(),
            )
    return job


def _extraction_job_ttl_sec() -> float:
    return max(300.0, float(os.getenv("MODULE2_EXTRACT_JOB_TTL_SEC", "7200")))


def _extraction_job_cap() -> int:
    return max(16, int(os.getenv("MODULE2_EXTRACT_JOB_CAP", "240")))


def _cleanup_extraction_jobs_locked() -> None:
    ttl_sec = _extraction_job_ttl_sec()
    cap = _extraction_job_cap()
    now_ts = time.time()
    removed_job_ids = [
        job_id
        for job_id, job in extraction_jobs.items()
        if job.terminal() and (now_ts - float(job.updated_at)) > ttl_sec
    ]
    for job_id in removed_job_ids:
        extraction_jobs.pop(job_id, None)
    if len(extraction_jobs) > cap:
        ordered_terminal = sorted(
            [item for item in extraction_jobs.values() if item.terminal()],
            key=lambda item: float(item.updated_at),
        )
        removable = max(0, len(extraction_jobs) - cap)
        for item in ordered_terminal[:removable]:
            removed_job_ids.append(item.job_id)
            extraction_jobs.pop(item.job_id, None)
    for job_id in removed_job_ids:
        _drop_extraction_job_runtime(job_id, remove_snapshot=True)


def _resolve_trace_artifact_ref(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    image_fragment = _artifact_fragment_from_path(payload.get("image_path"))
    if image_fragment:
        return image_fragment, _artifact_url_from_fragment(image_fragment)

    direct_url = str(payload.get("artifact_url") or "").strip()
    if direct_url:
        return None, direct_url

    for key in ("artifact_path",):
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

    def _table_dataframe_payload(table: Dict[str, Any]) -> Dict[str, Any]:
        headers = [str(x or "").strip() for x in table.get("headers", []) if str(x or "").strip()]
        rows_full: List[List[str]] = []
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            values: List[str] = []
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    values.append("")
                    continue
                text = str(cell.get("text") or "").strip()
                values.append(text[:200])
            if any(v for v in values):
                rows_full.append(values)
        col_count = max((len(row) for row in rows_full), default=len(headers))
        return {
            "headers": headers,
            "rows": rows_full,
            "row_count": len(rows_full),
            "col_count": col_count,
        }

    def _table_preview_payload(table: Dict[str, Any], max_rows: int = 5, max_cols: int = 6) -> Dict[str, Any]:
        dataframe = _table_dataframe_payload(table)
        headers = [str(x or "").strip() for x in dataframe.get("headers", [])][:max_cols]
        rows_preview: List[List[str]] = []
        for row in dataframe.get("rows", [])[:max_rows]:
            if not isinstance(row, list):
                continue
            values = [str(cell or "").strip()[:80] for cell in row[:max_cols]]
            if any(v for v in values):
                rows_preview.append(values)
        return {
            "headers": headers,
            "rows": rows_preview,
            "row_count": int(dataframe.get("row_count", 0) or 0),
            "col_count": int(dataframe.get("col_count", 0) or 0),
        }

    def _figure_dataframe_payload(figure: Dict[str, Any]) -> Dict[str, Any]:
        dataframe_raw = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
        headers = [
            str(x).strip()
            for x in (dataframe_raw.get("headers") if isinstance(dataframe_raw.get("headers"), list) else [])
            if str(x).strip()
        ]
        rows_full: List[List[str]] = []
        rows_raw = dataframe_raw.get("rows") if isinstance(dataframe_raw.get("rows"), list) else []
        for row in rows_raw:
            if not isinstance(row, list):
                continue
            vals = [str(v).strip()[:200] for v in row]
            if any(vals):
                rows_full.append(vals)
        col_count = max((len(row) for row in rows_full), default=len(headers))
        return {
            "headers": headers,
            "rows": rows_full,
            "row_count": len(rows_full),
            "col_count": col_count,
        }

    def _artifact_source_key(payload: Dict[str, Any]) -> str:
        if str(payload.get("image_path") or "").strip():
            return "pdf_mineru"
        if str(payload.get("artifact_path") or "").strip() or str(payload.get("artifact_url") or "").strip():
            return "pdf_roi_crop"
        return ""

    def _table_dataframe_source_key(table: Dict[str, Any]) -> str:
        source = str(table.get("source") or "").strip().lower()
        if "gemini" in source or "vision" in source:
            return "gemini_vision_table"
        return "table_structured"

    def _figure_dataframe_source_key(figure: Dict[str, Any]) -> str:
        dataframe_source = str(figure.get("dataframe_source") or "").strip().lower()
        if dataframe_source:
            return dataframe_source
        source = str(figure.get("source") or "").strip().lower()
        if "gemini" in source or "vision" in source:
            return "gemini_vision_figure"
        return "none"

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
            "dataframe": _table_dataframe_payload(table),
            "artifact_source": _artifact_source_key(table),
            "dataframe_source": _table_dataframe_source_key(table),
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
        dataframe_payload = _figure_dataframe_payload(figure)
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
            "dataframe": dataframe_payload,
            "artifact_source": _artifact_source_key(figure),
            "dataframe_source": _figure_dataframe_source_key(figure),
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
        "auto_result_filter_removed:",
    )
    noisy_exact = {
        "quality_gate_ok",
    }
    return _normalize_soft_warnings(
        [
            item
            for item in warnings
            if str(item or "").strip() not in noisy_exact
            and not any(str(item or "").startswith(prefix) for prefix in noisy_prefixes)
        ]
    )


def _promote_visual_diagnostics(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(diagnostics, dict):
        return {}
    merged = dict(diagnostics)
    parse_stats = merged.get("parse_stats") if isinstance(merged.get("parse_stats"), dict) else {}
    for key in (
        "chain_status",
        "artifact_status",
        "vision_status",
        "visual_baseline_artifact_ready",
        "mineru_item_count",
        "mineru_image_asset_count",
        "mineru_content_list_present",
        "mineru_markdown_present",
        "visual_selected_object_count",
        "visual_vision_candidate_count",
        "visual_vision_attempted_count",
        "visual_vision_success_count",
        "visual_vision_empty_count",
    ):
        if key in parse_stats and key not in merged:
            merged[key] = parse_stats.get(key)

    if "mineru_status" not in merged:
        mineru_status = ""
        mineru_run = parse_stats.get("mineru_run") if isinstance(parse_stats.get("mineru_run"), dict) else {}
        if mineru_run:
            mineru_status = str(mineru_run.get("status", "") or "").strip()
        if not mineru_status:
            chain_contract = merged.get("chain_contract") if isinstance(merged.get("chain_contract"), dict) else {}
            mineru_status = str(chain_contract.get("mineru_status", "") or "").strip()
        if mineru_status:
            merged["mineru_status"] = mineru_status
    return merged


def _resolve_module2_path(raw_value: str, default_path: Path) -> Path:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_path.resolve()
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()

    candidate_module2 = (MODULE2_ROOT / path).resolve()
    candidate_repo = (MODULE2_ROOT.parents[1] / path).resolve()
    normalized = raw.replace("\\", "/").lower()
    if normalized.startswith("backend/module2/"):
        return candidate_repo
    if candidate_repo.exists() and not candidate_module2.exists():
        return candidate_repo
    return candidate_module2


def _artifact_root_dir() -> Path:
    configured = os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "backend/module2/artifacts")
    root = _resolve_module2_path(configured, MODULE2_ROOT / "artifacts")
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


def _module4_document_sync_enabled() -> bool:
    return (os.getenv("MODULE2_MODULE4_DOCUMENT_SYNC_ENABLED", "false") or "false").lower() in {"1", "true", "yes"}


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _track_module4_sync_task(task: asyncio.Task[Any], *, outbox_id: str = "") -> asyncio.Task[Any]:
    module4_sync_tasks.add(task)
    outbox_key = str(outbox_id or "").strip()
    if outbox_key:
        module4_sync_task_index[outbox_key] = task

    def _cleanup(done: asyncio.Task[Any]) -> None:
        module4_sync_tasks.discard(done)
        if outbox_key:
            current = module4_sync_task_index.get(outbox_key)
            if current is done:
                module4_sync_task_index.pop(outbox_key, None)
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("module2 module4 sync task crashed: %s: %s", type(exc).__name__, exc)

    task.add_done_callback(_cleanup)
    return task


def _module4_outbox_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload_json")
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


async def _module4_post_sync_once(*, endpoint: str, tenant_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{_module4_base_url()}{endpoint}"
    headers = _module4_headers(tenant_id)
    timeout_sec = _module4_sync_timeout_sec()
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _post() -> Tuple[int, str]:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), body

    status, body = await asyncio.to_thread(_post)
    if status >= 400:
        raise RuntimeError(f"HTTP {status}: {body[:300]}")
    try:
        loaded = json.loads(body)
        return dict(loaded) if isinstance(loaded, dict) else {}
    except Exception:
        return {}


async def _deliver_module4_sync_outbox(outbox_id: str) -> None:
    key = str(outbox_id or "").strip()
    if not key:
        return

    while True:
        row = await storage.get_graph_sync_outbox(key)
        if not row:
            return
        if str(row.get("status") or "") == "delivered":
            return

        next_attempt_at = row.get("next_attempt_at")
        if isinstance(next_attempt_at, datetime):
            delay_sec = (next_attempt_at - _utcnow()).total_seconds()
            if delay_sec > 0:
                await asyncio.sleep(min(delay_sec, 30.0))
                continue

        claimed = await storage.claim_graph_sync_outbox(key)
        if not claimed:
            return

        endpoint = str(claimed.get("endpoint") or "").strip()
        tenant_id = str(claimed.get("tenant_id") or _module4_default_tenant()).strip() or _module4_default_tenant()
        source_value = str(claimed.get("source") or "module2").strip() or "module2"
        source_batch_key = str(claimed.get("source_batch_key") or "").strip()
        file_hash = str(claimed.get("file_hash") or "").strip()
        payload = _module4_outbox_payload(claimed)
        attempt_count = max(1, int(claimed.get("attempt_count") or 1))
        max_attempts = max(1, int(claimed.get("max_attempts") or (_module4_sync_retries() + 1)))

        module4_sync_metrics["attempted_batches"] = int(module4_sync_metrics.get("attempted_batches", 0)) + 1

        try:
            response_payload = await _module4_post_sync_once(
                endpoint=endpoint,
                tenant_id=tenant_id,
                payload=payload,
            )
            await storage.mark_graph_sync_outbox_delivered(
                outbox_id=key,
                response_payload=response_payload,
            )
            module4_sync_metrics["succeeded_batches"] = int(module4_sync_metrics.get("succeeded_batches", 0)) + 1
            module4_sync_metrics["last_error"] = ""
            module4_sync_metrics["last_success_at"] = time.time()
            module4_sync_metrics["last_job_id"] = str(response_payload.get("job_id") or "")
            module4_sync_metrics["last_batch_id"] = str(response_payload.get("batch_id") or "")
            module4_sync_metrics["last_endpoint"] = endpoint
            module4_sync_metrics["last_source_batch_key"] = source_batch_key
            logger.info(
                "module2 delivered module4 sync outbox=%s source=%s file=%s batch=%s attempt=%s/%s endpoint=%s",
                key,
                source_value,
                file_hash or "n/a",
                source_batch_key,
                attempt_count,
                max_attempts,
                endpoint,
            )
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            retryable = _module4_sync_retryable_status(int(getattr(exc, "code", 0) or 0))
            message = f"HTTPError {getattr(exc, 'code', 'unknown')}: {detail[:400]}"
        except Exception as exc:
            retryable = True
            message = f"{type(exc).__name__}: {exc}"

        if attempt_count < max_attempts and retryable:
            delay = _module4_sync_delay_sec(attempt_count)
            await storage.requeue_graph_sync_outbox(
                outbox_id=key,
                error_message=message,
                next_attempt_at=_utcnow() + timedelta(seconds=delay),
            )
            logger.warning(
                "module2 -> module4 outbox retry scheduled in %.1fs outbox=%s file=%s batch=%s attempt=%s/%s: %s",
                delay,
                key,
                file_hash or "n/a",
                source_batch_key,
                attempt_count,
                max_attempts,
                message,
            )
            await asyncio.sleep(delay)
            continue

        await storage.mark_graph_sync_outbox_failed(outbox_id=key, error_message=message)
        module4_sync_metrics["failed_batches"] = int(module4_sync_metrics.get("failed_batches", 0)) + 1
        module4_sync_metrics["last_error"] = message[:400]
        module4_sync_metrics["last_endpoint"] = endpoint
        module4_sync_metrics["last_source_batch_key"] = source_batch_key
        logger.warning(
            "module2 -> module4 outbox permanently failed outbox=%s file=%s batch=%s attempt=%s/%s: %s",
            key,
            file_hash or "n/a",
            source_batch_key,
            attempt_count,
            max_attempts,
            message,
        )
        return


def _schedule_module4_sync_outbox(outbox_id: str) -> None:
    key = str(outbox_id or "").strip()
    if not key or not _module4_sync_enabled():
        return
    current = module4_sync_task_index.get(key)
    if current and not current.done():
        return
    _track_module4_sync_task(
        asyncio.create_task(_deliver_module4_sync_outbox(key)),
        outbox_id=key,
    )


async def _enqueue_module4_document_sync(*, source: str, tenant_id: str, documents: List[Any], source_batch_key: str) -> None:
    if not _module4_document_sync_enabled():
        return
    normalized_docs = _module4_normalize_documents(documents)
    if not normalized_docs:
        return
    single_file_hash = ""
    if len(normalized_docs) == 1 and isinstance(normalized_docs[0], dict):
        single_file_hash = str(normalized_docs[0].get("file_hash") or "").strip()
    row = await storage.upsert_graph_sync_outbox(
        tenant_id=tenant_id,
        source=source,
        source_batch_key=source_batch_key,
        endpoint="/module4/ingest",
        payload={
            "tenant_id": tenant_id,
            "source": source,
            "source_batch_key": source_batch_key,
            "documents": normalized_docs,
        },
        sync_kind="document_batch",
        file_hash=single_file_hash or None,
        max_attempts=_module4_sync_retries() + 1,
    )
    if row:
        _schedule_module4_sync_outbox(str(row.get("outbox_id") or ""))


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


def _module4_sync_payload_summary(payload: Dict[str, Any], *, doc_limit: int = 12) -> Dict[str, Any]:
    data = dict(payload or {})
    documents = data.get("documents") if isinstance(data.get("documents"), list) else []
    doc_summaries: List[Dict[str, Any]] = []
    for item in documents[:doc_limit]:
        doc = dict(item) if isinstance(item, dict) else {}
        result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
        trace_hits = doc.get("trace_hits") if isinstance(doc.get("trace_hits"), list) else []
        errors = doc.get("errors") if isinstance(doc.get("errors"), list) else []
        soft_warnings = doc.get("soft_warnings") if isinstance(doc.get("soft_warnings"), list) else []
        diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
        doc_summaries.append(
            {
                "file_name": str(doc.get("file_name") or "").strip(),
                "file_hash": str(doc.get("file_hash") or "").strip(),
                "track": str(doc.get("track") or "").strip(),
                "field_count": len(result),
                "trace_hit_count": len(trace_hits),
                "error_count": len(errors),
                "soft_warning_count": len(soft_warnings),
                "quality_status": str(diagnostics.get("quality_status") or "").strip(),
                "cached": bool(doc.get("cached", False)),
            }
        )
    return {
        "tenant_id": str(data.get("tenant_id") or "").strip(),
        "source": str(data.get("source") or "").strip(),
        "source_batch_key": str(data.get("source_batch_key") or "").strip(),
        "document_count": len(documents),
        "documents": doc_summaries,
        "documents_truncated": len(documents) > doc_limit,
    }


def _module4_sync_response_summary(payload: Any) -> Dict[str, Any]:
    data = dict(payload) if isinstance(payload, dict) else {}
    return {
        "job_id": str(data.get("job_id") or "").strip(),
        "batch_id": str(data.get("batch_id") or "").strip(),
        "status": str(data.get("status") or "").strip(),
    }


def _serialize_module4_sync_outbox_row(row: Dict[str, Any], *, include_payload: bool = False) -> Dict[str, Any]:
    payload = row.get("payload_json")
    payload_data = dict(payload) if isinstance(payload, dict) else {}
    response_payload = row.get("last_response_json")
    response_data = dict(response_payload) if isinstance(response_payload, dict) else {}

    def _ts(value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        text = str(value or "").strip()
        return text or None

    view = {
        "outbox_id": str(row.get("outbox_id") or "").strip(),
        "tenant_id": str(row.get("tenant_id") or "").strip(),
        "source": str(row.get("source") or "").strip(),
        "source_batch_key": str(row.get("source_batch_key") or "").strip(),
        "endpoint": str(row.get("endpoint") or "").strip(),
        "sync_kind": str(row.get("sync_kind") or "").strip(),
        "file_hash": str(row.get("file_hash") or "").strip(),
        "status": str(row.get("status") or "").strip(),
        "attempt_count": int(row.get("attempt_count") or 0),
        "max_attempts": int(row.get("max_attempts") or 0),
        "last_error": str(row.get("last_error") or "").strip(),
        "next_attempt_at": _ts(row.get("next_attempt_at")),
        "last_attempt_at": _ts(row.get("last_attempt_at")),
        "delivered_at": _ts(row.get("delivered_at")),
        "created_at": _ts(row.get("created_at")),
        "updated_at": _ts(row.get("updated_at")),
        "payload_summary": _module4_sync_payload_summary(payload_data),
        "response_summary": _module4_sync_response_summary(response_data),
    }
    if include_payload:
        view["payload_json"] = payload_data
        view["last_response_json"] = response_data
    return view


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


async def _recover_module4_sync_outbox() -> None:
    if not _module4_sync_enabled():
        return
    rows = await storage.recover_pending_graph_sync_outbox(limit=200)
    for row in rows:
        _schedule_module4_sync_outbox(str(row.get("outbox_id") or ""))


async def _recover_extraction_jobs() -> None:
    recovered = 0
    resumed = 0
    for snapshot_path in sorted(_extraction_job_state_root_dir().glob("*.json")):
        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "module2 failed to parse extraction job snapshot path=%s: %s: %s",
                snapshot_path,
                type(exc).__name__,
                exc,
            )
            continue
        if not isinstance(payload, dict):
            continue
        job = _deserialize_extraction_job_state(payload.get("job"))
        if not job:
            continue
        runtime_spec = _normalize_extraction_job_runtime_spec(payload.get("runtime"))
        async with extraction_lock:
            _cleanup_extraction_jobs_locked()
            extraction_jobs[job.job_id] = job
            extraction_job_runtime_specs[job.job_id] = runtime_spec
        recovered += 1
        if job.terminal():
            continue
        try:
            loaded_files = _load_extraction_job_loaded_files(runtime_spec)
        except Exception as exc:
            await _mark_extraction_job_resume_failed(
                job.job_id,
                f"resume_payload_unavailable: {type(exc).__name__}: {exc}",
            )
            continue
        if not loaded_files:
            await _mark_extraction_job_resume_failed(
                job.job_id,
                "resume_payload_unavailable: no resumable uploaded files found",
            )
            continue
        if _schedule_extraction_job_task(
            job_id=job.job_id,
            loaded_files=loaded_files,
            schema_obj=runtime_spec.get("schema") if isinstance(runtime_spec.get("schema"), dict) else {},
            schema_digest=str(runtime_spec.get("schema_digest") or "").strip(),
            max_retries=max(0, int(runtime_spec.get("max_retries") or 0)),
            tenant_id=str(runtime_spec.get("tenant_id") or "").strip(),
        ):
            resumed += 1
    if recovered > 0:
        logger.info("module2 recovered extraction jobs=%s resumed=%s", recovered, resumed)


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
        "schema": payload.schema_payload,
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


def _clear_directory_contents(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
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


def _clear_module2_materialized_dirs() -> int:
    removed = 0
    seen: Set[str] = set()
    candidates = [
        _artifact_root_dir(),
        MODULE2_ROOT / ".mcache",
        _extraction_job_state_root_dir(),
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved).lower() if os.name == "nt" else str(resolved)
        if key in seen:
            continue
        seen.add(key)
        removed += _clear_directory_contents(resolved)
    return removed


async def _clear_extraction_runtime_state() -> None:
    pending_tasks = [task for task in extraction_job_tasks.values() if not task.done()]
    for task in pending_tasks:
        task.cancel()
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)
    async with extraction_lock:
        extraction_jobs.clear()
        extraction_job_runtime_specs.clear()
        extraction_job_persist_markers.clear()
        extraction_job_tasks.clear()
    async with office_preview_lock:
        office_preview_jobs.clear()


async def _clear_module4_sync_runtime_state() -> None:
    pending_tasks = list(module4_sync_tasks)
    for task in pending_tasks:
        task.cancel()
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)
    module4_sync_tasks.clear()
    module4_sync_task_index.clear()


@app.on_event("startup")
async def startup_event() -> None:
    await storage.connect()
    await _recover_module4_sync_outbox()
    await _recover_extraction_jobs()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    for job_id in list(extraction_jobs.keys()):
        await _persist_extraction_job_snapshot(job_id, force=True)
    running_extraction_tasks = [task for task in extraction_job_tasks.values() if not task.done()]
    if running_extraction_tasks:
        for task in running_extraction_tasks:
            task.cancel()
        await asyncio.gather(*running_extraction_tasks, return_exceptions=True)
    extraction_job_tasks.clear()
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
    module4_sync_task_index.clear()
    await storage.close()
    _shutdown_process_pool(_current_process_pool(), reason="app_shutdown")


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
        file_hash = ""
        async with office_preview_lock:
            job = office_preview_jobs.get(job_id)
            if not job:
                return
            file_hash = str(job.file_hash or "").strip().lower()
        frag = str(convert_meta.get("artifact_path") or "").strip()
        url = str(convert_meta.get("artifact_url") or "").strip()
        if not frag or not url:
            frag, url = _write_office_preview_artifact(
                file_name=file_name,
                file_hash=file_hash,
                pdf_bytes=pdf_bytes,
                convert_meta=convert_meta,
            )
        async with office_preview_lock:
            job = office_preview_jobs.get(job_id)
            if not job:
                return
            job.status = "completed"
            job.updated_at = time.time()
            job.artifact_path = frag
            job.artifact_url = url
            job.error = ""
            job.converter = str(convert_meta.get("converter", "") or "")
            job.elapsed_ms = int(convert_meta.get("elapsed_ms", 0) or 0)
    except Exception as exc:
        async with office_preview_lock:
            job = office_preview_jobs.get(job_id)
            if not job:
                return
            job.status = "failed"
            job.updated_at = time.time()
            job.error = f"{type(exc).__name__}: {exc}"
            job.converter = ""
            job.elapsed_ms = 0


async def _process_single_doc_bytes(
    file_name: str,
    file_bytes: bytes,
    schema: Dict[str, Any],
    schema_hash: str,
    max_retries: int,
    progress_hook: Optional[Callable[[str, float, str, Dict[str, Any]], Awaitable[None]]] = None,
) -> DocumentExtractionResponse:
    t0 = time.perf_counter()
    router = StreamRouter(storage)
    decision = await router.triage(file_name, file_bytes, schema_hash)

    async def _emit_progress(
        stage: str,
        ratio: float,
        message: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if progress_hook is None:
            return
        try:
            await progress_hook(
                str(stage or "").strip() or "running",
                max(0.0, min(1.0, float(ratio))),
                str(message or "").strip(),
                dict(extra or {}),
            )
        except Exception:
            return

    if decision.cached_payload is not None:
        await _emit_progress("cached", 1.0, "命中缓存，正在恢复抽取结果")
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
        cached_diag = _promote_visual_diagnostics(
            dict(cached_diag_raw) if isinstance(cached_diag_raw, dict) else {}
        )
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

    await _emit_progress("preflight", 0.05, "已接收文件，正在执行预检查")
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
    preparsed_output: Optional[
        tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]
    ] = None
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
            await _emit_progress("converting", 0.14, "正在将文档转换为 PDF 解析链路")
            preview_job = await _ensure_office_preview_job_started(
                file_name=file_name,
                file_bytes=file_bytes,
                file_hash=decision.file_hash,
            )
            try:
                pdf_bytes, preview_meta = await _run_with_progress_heartbeat(
                    _await_or_reuse_office_preview_pdf(
                        file_name=file_name,
                        file_hash=decision.file_hash,
                        timeout_sec=convert_timeout_sec,
                    ),
                    emit_progress=_emit_progress,
                    stage="converting",
                    base_ratio=0.14,
                    ceiling_ratio=0.23,
                    ramp_sec=min(max(6.0, convert_timeout_sec * 0.7), 18.0),
                    message="正在抽取字段、表格、图片与溯源信息",
        )
            except TimeoutError as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"Word 预览转 PDF 长时间未完成，无法继续处理 {file_name}: {exc}",
                ) from exc

            if pdf_bytes is None:
                preview_error = str(preview_meta.get("office_pdf_preview_error", "") or "").strip() or str(
                    preview_job.error or "office_preview_failed"
                )
                raise RuntimeError(preview_error)

            convert_meta = {
                "converter": str(preview_meta.get("converter", "") or preview_job.converter or "preview_job"),
                "elapsed_ms": int(preview_meta.get("elapsed_ms", 0) or preview_job.elapsed_ms or 0),
            }
            frag = str(preview_meta.get("artifact_path") or preview_job.artifact_path or "").strip()
            url = str(preview_meta.get("artifact_url") or preview_job.artifact_url or "").strip()

            parse_input_name = f"{Path(file_name).stem}.pdf"
            parse_input_bytes = pdf_bytes
            parse_track = "VisualTrack"
            conversion_diag = {
                "office_pdf_converted": True,
                "office_pdf_converter": str(convert_meta.get("converter", "")),
                "office_pdf_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
                "office_pdf_timeout_sec": round(convert_timeout_sec, 3),
                "office_pdf_preview_path": frag,
                "office_pdf_preview_url": url,
                "office_pdf_preview_reused": True,
                "office_pdf_preview_job_id": str(
                    preview_meta.get("office_pdf_preview_job_id", "") or preview_job.job_id or ""
                ),
                "office_pdf_preview_waited_ms": int(preview_meta.get("waited_ms", 0) or 0),
                "office_pdf_total_ms": int((time.perf_counter() - convert_t0) * 1000),
            }
            if str(preview_meta.get("office_pdf_preview_error", "") or "").strip():
                conversion_diag["office_pdf_preview_error"] = str(preview_meta.get("office_pdf_preview_error"))
            await _emit_progress("converting", 0.24, "文档已转换为 PDF，正在准备版面解析")
        except Exception as exc:
            conversion_diag = {
                "office_pdf_converted": False,
                "office_pdf_error": f"{type(exc).__name__}: {exc}",
                "office_pdf_timeout_sec": round(convert_timeout_sec, 3),
                "office_pdf_total_ms": int((time.perf_counter() - convert_t0) * 1000),
            }
            suffix = Path(file_name).suffix.lower()
            docx_native_recovery_requested = (
                suffix == ".docx"
                and _docx_native_recovery_enabled()
            )
            if docx_native_recovery_requested:
                conversion_diag["docx_native_recovery_requested"] = True
                conversion_diag["docx_native_recovery_reason"] = f"{type(exc).__name__}: {exc}"
            allow_native_fallback = (
                suffix == ".docx"
                and (os.getenv("MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK", "false").lower() in {"1", "true", "yes"})
            )
            if docx_native_recovery_requested:
                await _emit_progress("converting", 0.24, "Word PDF 链路失败，已切换 DOCX 原生恢复解析")
            if (not docx_native_recovery_requested) and ((word_parse_via_pdf and not allow_native_fallback) or suffix == ".doc"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Word 转 PDF 失败，无法处理 {file_name}: {type(exc).__name__}: {exc}",
                ) from exc
            if docx_native_recovery_requested:
                parse_track = "NativeDocx"
                parse_input_name = file_name
                parse_input_bytes = file_bytes
                parse_warning = "docx_native_recovery_after_pdf_failure"
            else:
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

    async def _try_docx_native_recovery(
        *,
        reason: str,
        timeout_hint_sec: Optional[float] = None,
    ) -> Optional[tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]]:
        if Path(file_name).suffix.lower() != ".docx":
            return None
        if not _docx_native_recovery_enabled():
            return None

        recovery_timeout_sec = max(
            12.0,
            float(os.getenv("MODULE2_DOCX_NATIVE_RECOVERY_TIMEOUT_SEC", "180")),
        )
        if timeout_hint_sec is not None:
            recovery_timeout_sec = min(recovery_timeout_sec, max(12.0, float(timeout_hint_sec)))
        if nonpdf_total_budget_sec is not None:
            elapsed_now = max(0.0, time.perf_counter() - t0)
            remaining_budget = nonpdf_total_budget_sec - elapsed_now - max(6.0, nonpdf_guard_sec)
            if remaining_budget <= 8.0:
                return None
            recovery_timeout_sec = min(recovery_timeout_sec, max(8.0, remaining_budget))

        parsed_output = await _run_parse_in_process_pool(
            loop=loop,
            file_bytes=file_bytes,
            file_name=file_name,
            track="NativeDocx",
            timeout_sec=recovery_timeout_sec,
            context_label=f"{file_name}:NativeDocx",
        )
        markdown, refs, tables, figures, stats = _unpack_parse_output(parsed_output)
        recovery_stats = dict(stats) if isinstance(stats, dict) else {}
        recovery_stats["docx_native_recovery"] = True
        recovery_stats["docx_native_recovery_reason"] = reason
        recovery_stats["docx_native_recovery_timeout_sec"] = round(recovery_timeout_sec, 3)
        return markdown, refs, tables, figures, recovery_stats

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

    parse_source_file_name = file_name if is_word_file(file_name) and parse_input_name.lower().endswith(".pdf") else None
    parse_source_file_bytes = file_bytes if parse_source_file_name else None

    await _emit_progress(
        "parsing",
        0.32,
        f"正在执行视觉解析：{parse_input_name}（MinerU 版面定位 -> ROI 裁剪 -> Gemini 图表理解）",
        {
            "parse_input_name": parse_input_name,
            "source_file_name": parse_source_file_name or "",
            "parse_track": parse_track,
        },
    )
    try:
        parsed_output = await _run_with_progress_heartbeat(
            _run_parse_in_process_pool(
                loop=loop,
                file_bytes=parse_input_bytes,
                file_name=parse_input_name,
                track=parse_track,
                timeout_sec=parse_timeout_sec,
                context_label=f"{file_name}:{parse_track}",
                source_file_name=parse_source_file_name,
                source_file_bytes=parse_source_file_bytes,
            ),
            emit_progress=_emit_progress,
            stage="parsing",
            base_ratio=0.32,
            ceiling_ratio=0.74,
            ramp_sec=_resolve_parse_progress_ramp_sec(
                parse_input_bytes_len=len(parse_input_bytes),
                timeout_sec=parse_timeout_sec,
            ),
            message=f"正在执行视觉解析：{parse_input_name}（MinerU 版面定位 -> ROI 裁剪 -> Gemini 图表理解）",
            extra={
                "parse_input_name": parse_input_name,
                "source_file_name": parse_source_file_name or "",
                "parse_track": parse_track,
            },
        )
        marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = _unpack_parse_output(parsed_output)
    except TimeoutError as exc:
        parse_input_is_pdf = parse_input_name.lower().endswith(".pdf")
        if parse_input_is_pdf and _visual_chain_required():
            raise HTTPException(
                status_code=504,
                detail=(
                    f"Required visual PDF chain timed out for {file_name}. "
                    "FastTrack/native fallback is disabled."
                ),
            ) from exc
        is_word_pdf_parse = is_word_file(file_name) and parse_input_is_pdf
        should_try_pdf_native_fallback = parse_track == "VisualTrack" and parse_input_is_pdf
        native_recovery = None
        if is_word_pdf_parse and word_suffix == ".docx":
            try:
                native_recovery = await _try_docx_native_recovery(
                    reason="word_pdf_parse_timeout",
                    timeout_hint_sec=parse_timeout_sec,
                )
            except Exception as recovery_exc:
                parse_warning = (
                    f"{parse_warning}|docx_native_recovery_failed:{type(recovery_exc).__name__}"
                    if parse_warning
                    else f"docx_native_recovery_failed:{type(recovery_exc).__name__}"
                )
        if native_recovery is not None:
            marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = native_recovery
            parse_track = "VisualTrack->NativeDocxRecoveryTimeout"
            parse_warning = (
                f"{parse_warning}|word_pdf_parse_timeout_recovered_native_docx"
                if parse_warning
                else "word_pdf_parse_timeout_recovered_native_docx"
            )
        elif is_word_pdf_parse or should_try_pdf_native_fallback:
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
                parsed_output = await _run_parse_in_process_pool(
                    loop=loop,
                    file_bytes=fallback_input_bytes,
                    file_name=fallback_input_name,
                    track="FastTrack",
                    timeout_sec=fallback_timeout,
                    context_label=f"{file_name}:FastTrackTimeoutFallback",
                    source_file_name=parse_source_file_name,
                    source_file_bytes=parse_source_file_bytes,
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
        if parse_track == "VisualTrack" and parse_input_name.lower().endswith(".pdf") and _visual_chain_required():
            if visual_backend_missing:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Required visual PDF chain is unavailable: OCR/MinerU dependencies are not ready. "
                        "FastTrack/native fallback is disabled."
                    ),
                ) from exc
            if visual_pipeline_unusable:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Required visual PDF chain failed: MinerU did not return a usable visual-first result. "
                        "FastTrack/native fallback is disabled."
                    ),
                ) from exc
        native_recovery = None
        if (
            parse_track == "VisualTrack"
            and parse_input_name.lower().endswith(".pdf")
            and word_suffix == ".docx"
            and (visual_backend_missing or visual_pipeline_unusable)
        ):
            try:
                native_recovery = await _try_docx_native_recovery(
                    reason="word_pdf_visual_error",
                    timeout_hint_sec=parse_timeout_sec,
                )
            except Exception as recovery_exc:
                parse_warning = (
                    f"{parse_warning}|docx_native_recovery_failed:{type(recovery_exc).__name__}"
                    if parse_warning
                    else f"docx_native_recovery_failed:{type(recovery_exc).__name__}"
                )
        if native_recovery is not None:
            marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = native_recovery
            parse_track = "VisualTrack->NativeDocxRecovery"
            parse_warning = (
                f"{parse_warning}|word_pdf_visual_recovered_native_docx"
                if parse_warning
                else "word_pdf_visual_recovered_native_docx"
            )
        elif parse_track == "VisualTrack" and parse_input_name.lower().endswith(".pdf"):
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
                if _disable_fasttrack_fallback():
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Required visual PDF chain failed and FastTrack/native fallback is disabled by "
                            "MODULE2_DISABLE_FASTTRACK_FALLBACK."
                        ),
                    ) from exc
                parse_track = "VisualTrack->FastTrackFallback"
                parse_warning = f"{parse_warning}|{fallback_warning}" if parse_warning else fallback_warning
                try:
                    parsed_output = await _run_parse_in_process_pool(
                        loop=loop,
                        file_bytes=parse_input_bytes,
                        file_name=parse_input_name,
                        track="FastTrack",
                        timeout_sec=parse_timeout_sec,
                        context_label=f"{file_name}:FastTrackFallback",
                        source_file_name=parse_source_file_name,
                        source_file_bytes=parse_source_file_bytes,
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
    logger.info(
        "module2 parse finished file=%s parse_input=%s track=%s tables=%s figures=%s refs=%s parse_ms=%s",
        file_name,
        parse_input_name,
        parse_track,
        len(table_blocks),
        len(figure_blocks),
        len(bbox_map),
        parse_ms,
    )
    chain_contract = _build_visual_chain_contract(
        file_name=file_name,
        parse_input_name=parse_input_name,
        parse_track=parse_track,
        word_parse_via_pdf=word_parse_via_pdf,
        conversion_diag=conversion_diag,
        parse_stats=parse_stats,
        table_blocks=table_blocks,
        figure_blocks=figure_blocks,
    )
    if chain_contract.get("required") and not chain_contract.get("satisfied"):
        reason_text = "; ".join(str(item) for item in (chain_contract.get("reasons") or [])[:8])
        raise HTTPException(
            status_code=503,
            detail=(
                f"Required visual chain contract failed for {file_name}: "
                f"{reason_text or 'unknown_reason'}"
            ),
        )
    await _emit_progress("parsed", 0.76, "版面解析完成，正在抽取字段与图表")

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
    logger.info(
        "module2 schema resolved file=%s source=%s field_count=%s",
        file_name,
        schema_meta.get("source", "unknown"),
        len(effective_schema_fields),
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
    await _emit_progress("extracting", 0.80, "正在抽取字段、表格、图片与溯源信息")
    try:
        final_state = await _run_with_progress_heartbeat(
            asyncio.wait_for(graph.run(init_state), timeout=extract_timeout_sec),
            emit_progress=_emit_progress,
            stage="extracting",
            base_ratio=0.80,
            ceiling_ratio=0.93,
            ramp_sec=_resolve_extract_progress_ramp_sec(
                timeout_sec=extract_timeout_sec,
                schema_field_count=len(effective_schema_fields),
                table_count=len(table_blocks),
                figure_count=len(figure_blocks),
            ),
            message="正在抽取字段、表格、图片与溯源信息",
        )
    except TimeoutError as exc:
        fallback_results = _quick_extract_from_tables(
            table_blocks=table_blocks,
            schema_fields=effective_schema_fields,
        )
        if str(schema_meta.get("mode", "")) == "auto" and not _disable_quick_table_fallback():
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
            detail = f"Extraction timed out for {file_name}"
            if str(schema_meta.get("mode", "")) == "auto" and _disable_quick_table_fallback():
                detail = (
                    f"Extraction timed out for {file_name}; quick table fallback is disabled by "
                    "MODULE2_DISABLE_QUICK_TABLE_FALLBACK."
                )
            raise HTTPException(status_code=504, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction graph failed for {file_name}: {exc}") from exc
    extract_ms = int((time.perf_counter() - extract_t0) * 1000)
    logger.info(
        "module2 graph finished file=%s result_fields=%s errors=%s soft_warnings=%s extract_ms=%s",
        file_name,
        len(final_state.get("results", {}) if isinstance(final_state.get("results", {}), dict) else {}),
        len(final_state.get("errors", []) if isinstance(final_state.get("errors", []), list) else []),
        len(final_state.get("soft_warnings", []) if isinstance(final_state.get("soft_warnings", []), list) else []),
        extract_ms,
    )
    await _emit_progress("finalizing", 0.96, "抽取完成，正在整理结果与缓存")
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
            if _is_low_value_auto_schema_field_name(field_name):
                dropped += 1
                continue
            try:
                confidence = float(entity.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if (
                confidence < min_conf
                or not _has_meaningful_value(entity.get("value"))
                or _is_low_value_quick_fallback_value(entity.get("value"))
            ):
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

    semantic_removed: Dict[str, str] = {}
    if str(schema_meta.get("mode", "")) == "auto" and final_results:
        filtered_results, semantic_removed = _filter_low_value_auto_results(final_results)
        if semantic_removed:
            final_results = filtered_results
            removed_count = len(semantic_removed)
            soft_warnings.append(f"auto_result_filter_removed:{removed_count}")

    quality_schema_fields = _effective_quality_schema_fields(effective_schema_fields, semantic_removed)
    quality_snapshot = _result_quality_snapshot(final_results, quality_schema_fields)
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
    if semantic_removed and not final_results:
        degraded_reasons.append("auto_results_all_filtered")
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
    if final_results:
        business_extraction_status = "nonempty"
    elif final_errors:
        business_extraction_status = "failed"
    else:
        business_extraction_status = "empty_valid"

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
        "quality_target_field_count": len(quality_schema_fields),
        "quality_target_fields": list(quality_schema_fields.keys())[:24],
        "auto_result_filter_removed_count": len(semantic_removed),
        "auto_result_filter_removed_fields": list(semantic_removed.keys())[:24],
        "quality_status": "degraded" if degraded_reasons else "ok",
        "quality_reasons": degraded_reasons,
        "quality_snapshot": quality_snapshot,
        "polymorphic_link_count": len(polymorphic_links),
        "polymorphic_links": polymorphic_links[:40],
        "business_extraction_status": business_extraction_status,
        "chain_contract": chain_contract,
    }
    if conversion_diag:
        diagnostics.update(conversion_diag)
    diagnostics.update(trace_stats)
    if parse_stats:
        parse_stats = dict(parse_stats)
        parse_stats["business_extraction_status"] = business_extraction_status
        diagnostics["parse_stats"] = parse_stats
        for key in (
            "chain_status",
            "artifact_status",
            "vision_status",
            "visual_baseline_artifact_ready",
            "mineru_item_count",
            "mineru_image_asset_count",
            "mineru_content_list_present",
            "mineru_markdown_present",
            "visual_selected_object_count",
            "visual_vision_candidate_count",
            "visual_vision_attempted_count",
            "visual_vision_success_count",
            "visual_vision_empty_count",
        ):
            if key in parse_stats:
                diagnostics[key] = parse_stats.get(key)
        mineru_run = parse_stats.get("mineru_run") if isinstance(parse_stats.get("mineru_run"), dict) else {}
        mineru_status = str(mineru_run.get("status", "") or "").strip()
        if mineru_status:
            diagnostics["mineru_status"] = mineru_status
        for key in (
            "plain_ext",
            "docx_chart_xml_seen",
            "docx_chart_xml_parsed",
            "docx_chart_xml_merged",
            "docx_chart_xml_unmatched",
            "docx_media_seen",
            "docx_media_used",
            "docx_media_parsed",
            "docx_media_parse_errors",
            "docx_media_skipped_duplicate",
            "docx_source_chart_merge_applied",
            "docx_source_chart_merge_ms",
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

    diagnostics = _promote_visual_diagnostics(diagnostics)

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

    await _emit_progress("completed", 1.0, "抽取完成")

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
) -> None:
    async with extraction_lock:
        job = extraction_jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = time.time()
    await _persist_extraction_job_snapshot(job_id, force=True)

    for file_index, (file_name, file_bytes, file_hash, artifact_path, artifact_url, _mime_type) in enumerate(
        loaded_files,
        start=1,
    ):
        doc_for_sync: Optional[DocumentExtractionResponse] = None
        async with extraction_lock:
            job_before_run = extraction_jobs.get(job_id)
            if not job_before_run:
                return
            if 0 <= (file_index - 1) < len(job_before_run.files):
                prior_state = job_before_run.files[file_index - 1]
                if prior_state.status in {"completed", "failed"}:
                    continue
        async def _update_progress(stage: str, ratio: float, message: str, extra: Dict[str, Any]) -> None:
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
            await _persist_extraction_job_snapshot(job_id, force=False)

        await _update_progress("queued", 0.0, "已进入解析队列", {})
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
                doc_for_sync = doc
                if doc.errors:
                    job_state.failed_files += 1
                    job_state.errors.append(f"{file_name}: {' | '.join(doc.errors)}")
                else:
                    job_state.completed_files += 1
                job_state.current_file_index = file_index
                job_state.current_file_name = file_name
                job_state.current_stage = "completed"
                job_state.updated_at = time.time()
            await _persist_extraction_job_snapshot(job_id, force=True)
            if doc_for_sync is not None and _module4_document_sync_enabled():
                source_batch_key = _module4_source_batch_key(
                    source="module2",
                    tenant_id=tenant_id,
                    documents=[doc_for_sync],
                    seed=f"extract_job_doc:{job_id}:{schema_digest}:{file_index}:{file_hash}",
                )
                try:
                    await _enqueue_module4_document_sync(
                        source="module2",
                        tenant_id=tenant_id,
                        documents=[doc_for_sync],
                        source_batch_key=source_batch_key,
                    )
                except Exception as sync_exc:
                    logger.warning(
                        "module2 failed to enqueue module4 document sync job=%s file=%s hash=%s: %s: %s",
                        job_id,
                        file_name,
                        file_hash,
                        type(sync_exc).__name__,
                        sync_exc,
                    )
                    async with extraction_lock:
                        job_state = extraction_jobs.get(job_id)
                        if job_state:
                            job_state.errors.append(
                                f"{file_name}: module4_sync_enqueue_failed: {type(sync_exc).__name__}: {sync_exc}"
                            )
                            job_state.updated_at = time.time()
                    await _persist_extraction_job_snapshot(job_id, force=True)
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
            await _persist_extraction_job_snapshot(job_id, force=True)

    final_documents: List[DocumentExtractionResponse] = []
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
        final_documents = list(job.documents)
    await _persist_extraction_job_snapshot(job_id, force=True)
    if final_documents and _module4_document_sync_enabled():
        source_batch_key = _module4_source_batch_key(
            source="module2",
            tenant_id=tenant_id,
            documents=final_documents,
            seed=f"extract_job_final:{job_id}:{schema_digest}",
        )
        try:
            await _enqueue_module4_document_sync(
                source="module2",
                tenant_id=tenant_id,
                documents=final_documents,
                source_batch_key=source_batch_key,
            )
        except Exception as sync_exc:
            logger.warning(
                "module2 failed to enqueue final module4 document sync job=%s: %s: %s",
                job_id,
                type(sync_exc).__name__,
                sync_exc,
            )
            async with extraction_lock:
                job_state = extraction_jobs.get(job_id)
                if job_state:
                    job_state.errors.append(f"module4_sync_enqueue_failed: {type(sync_exc).__name__}: {sync_exc}")
                    job_state.updated_at = time.time()
            await _persist_extraction_job_snapshot(job_id, force=True)


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
    schema_form: str = Form(..., alias="schema"),
    tenant_id: str = Form(default=""),
) -> Dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    schema_obj = _parse_schema_form_json(schema_form)
    await _ensure_provider_ready_for_job_create()

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
    resolved_tenant = _module4_tenant(request, tenant_id)
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
        extraction_job_runtime_specs[job_id] = {
            "schema": schema_obj,
            "schema_digest": schema_digest,
            "max_retries": max_retries,
            "tenant_id": resolved_tenant,
            "loaded_files": [
                {
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "artifact_path": artifact_path,
                    "artifact_url": artifact_url,
                    "mime_type": mime_type,
                }
                for file_name, _file_bytes, file_hash, artifact_path, artifact_url, mime_type in loaded_files
            ],
        }

    await _persist_extraction_job_snapshot(job_id, force=True)
    _schedule_extraction_job_task(
        job_id=job_id,
        loaded_files=loaded_files,
        schema_obj=schema_obj,
        schema_digest=schema_digest,
        max_retries=max_retries,
        tenant_id=resolved_tenant,
    )

    return _serialize_extraction_job(job_state, include_documents=False)


@app.get("/extract/jobs/status/{job_id}")
async def extract_jobs_status(job_id: str, include_documents: bool = False) -> Dict[str, Any]:
    normalized_job_id = str(job_id).strip()
    if normalized_job_id and not re.fullmatch(r"extract_job_[A-Za-z0-9]+", normalized_job_id):
        logger.warning("module2 unexpected extraction job status lookup job_id=%r", normalized_job_id)
    async with extraction_lock:
        _cleanup_extraction_jobs_locked()
        job = extraction_jobs.get(normalized_job_id)
    if not job:
        job = await _restore_extraction_job_from_snapshot(normalized_job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Extraction job not found")
    return _serialize_extraction_job(job, include_documents=include_documents)


@app.post("/extract/batch", response_model=BatchExtractionResponse)
async def extract_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    schema_form: str = Form(..., alias="schema"),
    tenant_id: str = Form(default=""),
) -> BatchExtractionResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    if len(files) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    schema_obj = _parse_schema_form_json(schema_form)
    await _ensure_provider_ready_for_job_create()

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

    if _module4_document_sync_enabled():
        resolved_tenant = _module4_tenant(request, tenant_id)
        source_batch_key = _module4_source_batch_key(
            source="module2",
            tenant_id=resolved_tenant,
            documents=results,
            seed=f"extract_batch:{schema_digest}",
        )
        await _enqueue_module4_document_sync(
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
    created = await _ensure_office_preview_job_started(
        file_name=file_name,
        file_bytes=file_bytes,
        file_hash=file_hash,
    )
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

    if sync_documents and _module4_document_sync_enabled():
        source_batch_key = _module4_source_batch_key(
            source="module2",
            tenant_id=tenant_id,
            documents=sync_documents,
            seed=f"dify_bridge:{request_id}:{schema_hash}",
        )
        await _enqueue_module4_document_sync(
            source="module2",
            tenant_id=tenant_id,
            documents=sync_documents,
            source_batch_key=source_batch_key,
        )


@app.post("/dify/module2/jobs/create")
async def dify_module2_jobs_create(request: Request, payload: BridgeJobCreateRequest) -> Dict[str, Any]:
    _bridge_check_token(request)

    if not isinstance(payload.schema_payload, dict):
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

    schema_hash = _schema_hash(payload.schema_payload)
    asyncio.create_task(
        _run_bridge_job(
            job_id=job_id,
            schema=payload.schema_payload,
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
    return await assistant_service.query_once(payload)


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
    await _clear_extraction_runtime_state()
    await _clear_module4_sync_runtime_state()
    cache_counts = await storage.clear_runtime_cache()
    removed_artifacts = _clear_module2_materialized_dirs()
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
    storage_diag = storage.diagnostics()
    provider_diag = _provider_preflight_snapshot()
    return {
        "status": "ok",
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "python_base_prefix": sys.base_prefix,
        "python_venv_active": str(sys.prefix != sys.base_prefix).lower(),
        "llm_provider_preflight_ok": str(bool(provider_diag.get("ok"))).lower(),
        "llm_provider_last_checked_at": str(provider_diag.get("checked_at", 0.0) or 0.0),
        "llm_provider_base_url": str(provider_diag.get("base_url", "") or ""),
        "llm_provider_model": str(provider_diag.get("model", "") or ""),
        "llm_provider_last_error": str(provider_diag.get("error", "") or ""),
        "bridge_jobs_in_memory": str(len(bridge_jobs)),
        "bridge_request_index_size": str(len(bridge_request_index)),
        "office_preview_jobs_in_memory": str(len(office_preview_jobs)),
        "module4_sync_enabled": str(_module4_sync_enabled()).lower(),
        "module4_sync_inflight_batches": str(len(module4_sync_tasks)),
        "module4_sync_inflight_outbox": str(len(module4_sync_task_index)),
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
        "storage_db_connected": str(storage_diag.get("db_connected", False)).lower(),
        "storage_degraded_memory_mode": str(storage_diag.get("degraded_memory_mode", False)).lower(),
        "storage_graph_sync_outbox_memory_size": str(storage_diag.get("graph_sync_outbox_memory_size", 0)),
    }


@app.get("/module4-sync/outbox")
async def module4_sync_outbox_list(
    tenant_id: str = Query(default=""),
    source: str = Query(default="module2"),
    source_batch_key: str = Query(default=""),
    endpoint: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    include_payload: bool = Query(default=False),
    include_future: bool = Query(default=True),
) -> Dict[str, Any]:
    statuses = [item.strip() for item in status.split(",") if item.strip()]
    rows = await storage.list_graph_sync_outbox(
        tenant_id=tenant_id or None,
        source=source or None,
        source_batch_key=source_batch_key or None,
        endpoint=endpoint or None,
        statuses=statuses or None,
        limit=limit,
        include_future=include_future,
    )
    return {
        "items": [_serialize_module4_sync_outbox_row(row, include_payload=include_payload) for row in rows],
        "count": len(rows),
        "filters": {
            "tenant_id": tenant_id.strip(),
            "source": source.strip(),
            "source_batch_key": source_batch_key.strip(),
            "endpoint": endpoint.strip(),
            "status": statuses,
            "limit": limit,
            "include_payload": include_payload,
            "include_future": include_future,
        },
        "metrics": {
            "attempted_batches": int(module4_sync_metrics.get("attempted_batches", 0) or 0),
            "succeeded_batches": int(module4_sync_metrics.get("succeeded_batches", 0) or 0),
            "failed_batches": int(module4_sync_metrics.get("failed_batches", 0) or 0),
            "last_error": str(module4_sync_metrics.get("last_error", "") or ""),
            "last_job_id": str(module4_sync_metrics.get("last_job_id", "") or ""),
            "last_batch_id": str(module4_sync_metrics.get("last_batch_id", "") or ""),
            "last_endpoint": str(module4_sync_metrics.get("last_endpoint", "") or ""),
            "last_source_batch_key": str(module4_sync_metrics.get("last_source_batch_key", "") or ""),
        },
    }


@app.get("/module4-sync/outbox/{outbox_id}")
async def module4_sync_outbox_detail(
    outbox_id: str,
    include_payload: bool = Query(default=True),
) -> Dict[str, Any]:
    row = await storage.get_graph_sync_outbox(outbox_id)
    if not row:
        raise HTTPException(status_code=404, detail="Module4 sync outbox row not found")
    return _serialize_module4_sync_outbox_row(row, include_payload=include_payload)

