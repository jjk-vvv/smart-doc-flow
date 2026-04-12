from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from app.core.config import Settings

RESERVED_PREFIXES = {"api", "extract", "module4", "gateway", "module1-placeholder"}

# Windows often maps `.mjs` to `text/plain`, which breaks browser module loading.
mimetypes.add_type("text/javascript", ".mjs")


def _frontend_unavailable_response(settings: Settings) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "message": "Frontend dist is not available yet. Build the frontend or use Vite dev server.",
            "frontend_dist_dir": str(settings.frontend_dist_dir),
        },
    )


def _safe_candidate(dist_dir: Path, requested_path: str) -> Path | None:
    normalized = requested_path.strip().lstrip("/")
    if not normalized:
        return None
    candidate = (dist_dir / normalized).resolve()
    if dist_dir.resolve() not in candidate.parents and candidate != dist_dir.resolve():
        return None
    return candidate


def serve_frontend_asset(settings: Settings, requested_path: str) -> Response:
    dist_dir = settings.frontend_dist_dir
    if not dist_dir.exists() or not dist_dir.is_dir():
        return _frontend_unavailable_response(settings)

    candidate = _safe_candidate(dist_dir, requested_path)
    if candidate and candidate.exists() and candidate.is_file():
        media_type = mimetypes.guess_type(str(candidate))[0] or None
        return FileResponse(candidate, media_type=media_type)

    index_file = dist_dir / "index.html"
    if index_file.exists():
        media_type = mimetypes.guess_type(str(index_file))[0] or None
        return FileResponse(index_file, media_type=media_type)

    raise HTTPException(status_code=404, detail="Frontend asset not found")
