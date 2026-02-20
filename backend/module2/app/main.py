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


def _max_workers() -> int:
    cpu = os.cpu_count() or 4
    return min(max(cpu - 1, 2), 8)


process_pool = ProcessPoolExecutor(max_workers=_max_workers())

app = FastAPI(title="A23 Module 2 - Unstructured Document Extraction", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail=f"Empty file: {file_name}")

    router = StreamRouter(storage)
    decision = await router.triage(file_name, file_bytes, schema_hash)

    if decision.cached_payload is not None:
        cached_result = decision.cached_payload.get("result", {})
        return DocumentExtractionResponse(
            file_name=file_name,
            file_hash=decision.file_hash,
            track=decision.track,
            cached=True,
            result=ExtractionResult(cached_result),
            errors=[],
        )

    loop = asyncio.get_running_loop()
    parse_timeout_sec = float(os.getenv("MODULE2_PARSE_TIMEOUT_SEC", "120"))
    parse_t0 = time.perf_counter()
    try:
        marked_markdown, bbox_map, table_blocks = await asyncio.wait_for(
            loop.run_in_executor(process_pool, parse_document_in_subprocess, file_bytes, file_name, decision.track),
            timeout=parse_timeout_sec,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"Native parsing timed out for {file_name}") from exc
    except Exception as exc:
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

    response = DocumentExtractionResponse(
        file_name=file_name,
        file_hash=decision.file_hash,
        track=decision.track,
        cached=False,
        result=ExtractionResult(final_state.get("results", {})),
        errors=final_state.get("errors", []),
    )

    await storage.save_extraction_result(
        decision.cache_key,
        {
            "file_name": file_name,
            "file_hash": decision.file_hash,
            "schema_hash": schema_hash,
            "cache_key": decision.cache_key,
            "track": decision.track,
            "cached": False,
            "result": response.result.model_dump(mode="json"),
            "errors": response.errors,
            "metrics": {
                "parse_ms": parse_ms,
                "extract_ms": extract_ms,
                "total_ms": total_ms,
                "markdown_len": len(marked_markdown),
                "refs": len(bbox_map),
                "table_count": len(table_blocks),
                "table_cells": _count_table_cells(table_blocks),
                "table_quality_avg": _table_quality_avg(table_blocks),
            },
            "tables": table_blocks,
        },
    )

    return response


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

    schema_digest = _schema_hash(schema_obj)
    max_retries = max(0, min(int(os.getenv("MODULE2_MAX_RETRIES", "2")), 6))
    concurrency = max(1, min(int(os.getenv("MODULE2_BATCH_CONCURRENCY", "2")), len(files)))
    sem = asyncio.Semaphore(concurrency)

    async def _run(file: UploadFile) -> DocumentExtractionResponse:
        async with sem:
            return await process_single_doc(file, schema_obj, schema_digest, max_retries)

    tasks = [_run(file) for file in files]
    results = await asyncio.gather(*tasks)
    return BatchExtractionResponse(documents=results)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}
