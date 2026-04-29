from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ...core.config import get_settings
from ...services.office_online_preview_service import (
    OfficeOnlinePreviewError,
    create_office_online_preview,
    resolve_office_online_preview_file,
)


router = APIRouter()
public_router = APIRouter()


def _resolve_owner_id(request: Request) -> str:
    state_user = getattr(getattr(request, "state", None), "authenticated_user", None)
    return (
        str(getattr(state_user, "tenant_id", "") or "").strip()
        or str(getattr(state_user, "user_id", "") or "").strip()
        or str(request.headers.get("X-Authenticated-Tenant-Id") or "").strip()
        or str(request.headers.get("X-Authenticated-User-Id") or "").strip()
    )


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, OfficeOnlinePreviewError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/office-online/preview/start")
async def start_office_online_preview(request: Request, file: UploadFile = File(...)):
    settings = get_settings()
    file_name = str(file.filename or "").strip()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="empty office payload")
    if len(file_bytes) > settings.max_file_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"file size exceeds {settings.max_file_mb}MB limit",
        )

    try:
        return create_office_online_preview(
            request=request,
            owner_id=_resolve_owner_id(request),
            file_name=file_name,
            file_bytes=file_bytes,
        )
    except Exception as exc:
        raise _to_http_error(exc)


def _serve_office_online_preview_source(token: str) -> FileResponse:
    try:
        file_path, record = resolve_office_online_preview_file(token)
    except Exception as exc:
        raise _to_http_error(exc)

    filename = str(record.get("filename") or file_path.name).strip() or file_path.name
    encoded_name = urllib.parse.quote(filename)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=str(record.get("mime_type") or "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": (
                f"inline; filename={encoded_name}; "
                f"filename*=UTF-8''{encoded_name}"
            ),
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@public_router.get("/office-online/preview/public/{token}/{filename:path}", include_in_schema=False)
def get_office_online_preview_source(token: str, filename: str = "") -> FileResponse:
    return _serve_office_online_preview_source(token)


@public_router.head("/office-online/preview/public/{token}/{filename:path}", include_in_schema=False)
def head_office_online_preview_source(token: str, filename: str = "") -> FileResponse:
    return _serve_office_online_preview_source(token)


__all__ = ["public_router", "router"]
