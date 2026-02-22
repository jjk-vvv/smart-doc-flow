from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import AgentState, ExtractionGraph
from app.core.parser import parse_document_in_subprocess
from app.db.storage import ExtractionStorage
from app.schemas import BatchExtractionResponse, DocumentExtractionResponse, ExtractionResult


@dataclass
class RouteDecision:
    file_hash: str
    cache_key: str
    track: str
    cached_payload: Optional[Dict[str, Any]]


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


def _schema_hash(schema: Dict[str, Any]) -> str:
    normalized = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _count_table_cells(table_blocks: List[Dict[str, Any]]) -> int:
    count = 0
    for table in table_blocks:
        for row in table.get("rows", []):
            count += len(row.get("cells", []))
    return count


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


@app.on_event("startup")
async def startup_event() -> None:
    await storage.connect()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await storage.close()
    process_pool.shutdown(wait=False, cancel_futures=True)


async def process_single_doc(
    file: UploadFile,
    schema: Dict[str, Any],
    schema_hash: str,
    max_retries: int,
) -> DocumentExtractionResponse:
    t0 = time.perf_counter()
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

    router = StreamRouter(storage)
    decision = await router.triage(file_name, file_bytes, schema_hash)

    if decision.cached_payload is not None:
        cached_result = decision.cached_payload.get("result", {})
        cached_errors_raw = decision.cached_payload.get("errors", [])
        cached_errors = [str(x) for x in cached_errors_raw] if isinstance(cached_errors_raw, list) else []
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
            diagnostics=cached_diag,
        )

    loop = asyncio.get_running_loop()
    parse_timeout_sec = float(os.getenv("MODULE2_PARSE_TIMEOUT_SEC", "120"))
    parse_t0 = time.perf_counter()
    parse_track = decision.track
    parse_warning: Optional[str] = None
    figure_blocks: List[Dict[str, Any]] = []

    def _unpack_parse_output(parsed: Any) -> tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        if isinstance(parsed, tuple):
            if len(parsed) == 4:
                markdown, refs, tables, figures = parsed
                return markdown, refs, tables, figures if isinstance(figures, list) else []
            if len(parsed) == 3:
                markdown, refs, tables = parsed
                return markdown, refs, tables, []
        raise ValueError("Unexpected parse output shape")

    try:
        parsed_output = await asyncio.wait_for(
            loop.run_in_executor(process_pool, parse_document_in_subprocess, file_bytes, file_name, parse_track),
            timeout=parse_timeout_sec,
        )
        marked_markdown, bbox_map, table_blocks, figure_blocks = _unpack_parse_output(parsed_output)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from exc
    except Exception as exc:
        message = str(exc)
        visual_backend_missing = (
            ("VisualTrack OCR backend is unavailable" in message)
            or ("rapidocr_onnxruntime" in message.lower())
            or ("pymupdf" in message.lower())
        )
        if parse_track == "VisualTrack" and file_name.lower().endswith(".pdf") and visual_backend_missing:
            parse_track = "VisualTrack->FastTrackFallback"
            parse_warning = (
                "VisualTrack OCR backend unavailable, auto-fallback to native FastTrack parsing."
            )
            try:
                parsed_output = await asyncio.wait_for(
                    loop.run_in_executor(process_pool, parse_document_in_subprocess, file_bytes, file_name, "FastTrack"),
                    timeout=parse_timeout_sec,
                )
                marked_markdown, bbox_map, table_blocks, figure_blocks = _unpack_parse_output(parsed_output)
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
            if "Unsupported file type" in message:
                raise HTTPException(status_code=400, detail=message) from exc
            if "backend is unavailable" in message.lower() or "please install" in message.lower():
                raise HTTPException(status_code=503, detail=message) from exc
            raise HTTPException(status_code=500, detail=f"Native parsing failed for {file_name}: {exc}") from exc
    parse_ms = int((time.perf_counter() - parse_t0) * 1000)

    init_state: AgentState = {
        "markdown": marked_markdown,
        "bbox_map": bbox_map,
        "table_blocks": table_blocks,
        "table_summary": "",
        "field_hints": {},
        "schema": schema,
        "results": {},
        "errors": [],
        "retries": 0,
        "max_retries": max_retries,
    }

    extract_timeout_sec = float(os.getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "120"))
    extract_t0 = time.perf_counter()
    try:
        final_state = await asyncio.wait_for(graph.run(init_state), timeout=extract_timeout_sec)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Extraction timed out for {file_name}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction graph failed for {file_name}: {exc}") from exc
    extract_ms = int((time.perf_counter() - extract_t0) * 1000)
    total_ms = int((time.perf_counter() - t0) * 1000)
    diagnostics = {
        "parse_ms": parse_ms,
        "extract_ms": extract_ms,
        "total_ms": total_ms,
        "markdown_len": len(marked_markdown),
        "refs": len(bbox_map),
        "table_count": len(table_blocks),
        "table_cells": _count_table_cells(table_blocks),
        "table_quality_avg": _table_quality_avg(table_blocks),
        "table_sources": _table_source_counts(table_blocks),
        "figure_count": len(figure_blocks),
        "figure_pages": _figure_pages(figure_blocks),
        "figure_sources": _figure_source_counts(figure_blocks),
    }

    response = DocumentExtractionResponse(
        file_name=file_name,
        file_hash=decision.file_hash,
        track=parse_track,
        cached=False,
        result=ExtractionResult(final_state.get("results", {})),
        errors=(([parse_warning] if parse_warning else []) + list(final_state.get("errors", []))),
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
            "diagnostics": diagnostics,
            "metrics": diagnostics,
            "tables": table_blocks,
            "figures": figure_blocks,
        },
    )

    return response


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


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}
