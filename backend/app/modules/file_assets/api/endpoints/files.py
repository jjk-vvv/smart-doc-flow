from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from ...service import (
    build_file_asset_urls,
    build_preview_text_for_owner,
    preview_support_for_suffix,
    resolve_file_for_owner,
)


router = APIRouter()


def _resolve_owner_id(request: Request) -> str:
    state_user = getattr(getattr(request, "state", None), "authenticated_user", None)
    owner_id = (
        str(getattr(state_user, "tenant_id", "") or "").strip()
        or str(getattr(state_user, "user_id", "") or "").strip()
        or str(request.headers.get("X-Authenticated-User-Id") or "").strip()
    )
    if not owner_id:
        raise HTTPException(status_code=401, detail="authenticated owner required")
    return owner_id


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/download/{file_id}")
def download_file_asset(file_id: str, request: Request) -> FileResponse:
    owner_id = _resolve_owner_id(request)
    try:
        record, file_path = resolve_file_for_owner(file_id, owner_id)
    except Exception as exc:  # pragma: no cover - thin HTTP adapter
        raise _to_http_error(exc)
    return FileResponse(
        path=str(file_path),
        filename=record["filename"] or file_path.name,
        media_type=record.get("mime_type") or "application/octet-stream",
    )


@router.get("/file-assets/{file_id}/download")
def download_file_asset_alias(file_id: str, request: Request) -> FileResponse:
    return download_file_asset(file_id, request)


@router.get("/file-assets/{file_id}/preview")
def preview_file_asset(
    file_id: str,
    request: Request,
    max_lines: int = Query(240, ge=20, le=1000),
    max_chars: int = Query(12000, ge=2000, le=80000),
) -> PlainTextResponse:
    owner_id = _resolve_owner_id(request)
    try:
        content = build_preview_text_for_owner(
            file_id,
            owner_id,
            max_lines=max_lines,
            max_chars=max_chars,
        )
    except Exception as exc:  # pragma: no cover - thin HTTP adapter
        raise _to_http_error(exc)
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.get("/file-assets/{file_id}")
def get_file_asset_metadata(file_id: str, request: Request) -> dict[str, Any]:
    owner_id = _resolve_owner_id(request)
    try:
        record, file_path = resolve_file_for_owner(file_id, owner_id)
    except Exception as exc:  # pragma: no cover - thin HTTP adapter
        raise _to_http_error(exc)
    links = build_file_asset_urls(record["file_id"])
    suffix = record.get("suffix") or file_path.suffix.lower()
    preview_supported, preview_reason = preview_support_for_suffix(suffix)
    return {
        "file_id": record["file_id"],
        "filename": record["filename"] or file_path.name,
        "suffix": suffix,
        "mime_type": record.get("mime_type") or "application/octet-stream",
        "size_bytes": int(record.get("size_bytes") or file_path.stat().st_size),
        "source_module": record.get("source_module") or "",
        "purpose": record.get("purpose") or "",
        "download_url": links["download_url"],
        "preview_url": links["preview_url"],
        "preview_supported": preview_supported,
        "preview_reason": preview_reason,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


__all__ = ["router"]
