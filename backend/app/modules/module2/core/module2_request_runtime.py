from __future__ import annotations

import json
import mimetypes
from typing import Any

from fastapi import HTTPException, Request, UploadFile

from app.modules.module2.core.config import get_extraction_settings
from app.services import gateway_service


def parse_schema_form_json(schema_form: str) -> dict[str, Any]:
    raw = str(schema_form or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Schema payload is required")
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Schema must be a JSON object")
    return payload


async def read_uploads_for_upstream(
    uploads: list[UploadFile],
) -> list[tuple[str, tuple[str, bytes, str]]]:
    max_file_mb = get_extraction_settings().max_file_mb
    max_file_bytes = max_file_mb * 1024 * 1024
    files_payload: list[tuple[str, tuple[str, bytes, str]]] = []
    for upload in uploads:
        file_name = upload.filename or "unknown"
        file_bytes = await upload.read(max_file_bytes + 1)
        if len(file_bytes) > max_file_bytes:
            raise HTTPException(status_code=413, detail=f"File too large: {file_name}. Max size is {max_file_mb}MB.")
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"Empty file: {file_name}")
        mime_type = str(upload.content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream").strip()
        files_payload.append(("files", (file_name, file_bytes, mime_type or "application/octet-stream")))
    return files_payload


def forward_module2_context_headers(
    request: Request,
    additional_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    blocked_headers = set(gateway_service.HOP_BY_HOP_HEADERS)
    blocked_headers.update({"content-length", "content-type"})
    forwarded: dict[str, str] = {}
    for key, value in request.headers.items():
        normalized_key = str(key or "").lower().strip()
        if normalized_key in blocked_headers:
            continue
        forwarded[key] = value
    for key, value in (additional_headers or {}).items():
        normalized_key = str(key or "").lower().strip()
        if not normalized_key or normalized_key in blocked_headers:
            continue
        forwarded[key] = value
    return forwarded


def normalize_cache_clear_scope(value: str) -> str:
    normalized = str(value or "results").strip().lower() or "results"
    if normalized not in {"results", "runtime", "all"}:
        raise HTTPException(status_code=400, detail="Invalid cache clear scope")
    return normalized
