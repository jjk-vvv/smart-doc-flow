from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.core.config import Settings

RESERVED_PREFIXES = {"api", "extract", "module1", "module3", "module4", "gateway"}
MOBILE_FRONTEND_PREFIX = "m"
FORCED_VIEW_QUERY_KEY = "view"
MOBILE_VIEW_VALUES = {"mobile", "app"}
DESKTOP_VIEW_VALUES = {"desktop", "web"}

# Windows often maps `.mjs` to `text/plain`, which breaks browser module loading.
mimetypes.add_type("text/javascript", ".mjs")


def _frontend_unavailable_response(dist_dir: Path, *, label: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "message": f"{label} frontend dist is not available yet. Build the frontend or use Vite dev server.",
            "frontend_dist_dir": str(dist_dir),
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


def _dist_available(dist_dir: Path | None) -> bool:
    return bool(dist_dir and dist_dir.exists() and dist_dir.is_dir())


def mobile_frontend_available(settings: Settings) -> bool:
    return _dist_available(settings.frontend_app_dist_dir)


def _normalized_forced_view(request: Request) -> str:
    return str(request.query_params.get(FORCED_VIEW_QUERY_KEY, "") or "").strip().lower()


def _request_prefers_mobile_view(request: Request) -> bool:
    return _normalized_forced_view(request) in MOBILE_VIEW_VALUES


def _request_forces_desktop_view(request: Request) -> bool:
    return _normalized_forced_view(request) in DESKTOP_VIEW_VALUES


def _is_probably_mobile_user_agent(request: Request) -> bool:
    user_agent = str(request.headers.get("user-agent", "") or "").strip().lower()
    if not user_agent:
        return False
    mobile_fragments = (
        "android",
        "iphone",
        "ipad",
        "ipod",
        "mobile",
        "harmony",
        "micromessenger",
        "windows phone",
    )
    return any(fragment in user_agent for fragment in mobile_fragments)


def is_mobile_frontend_path(requested_path: str) -> bool:
    first_segment = str(requested_path or "").split("/", 1)[0].strip().lower()
    return first_segment == MOBILE_FRONTEND_PREFIX


def strip_mobile_frontend_prefix(requested_path: str) -> str:
    normalized = str(requested_path or "").strip().lstrip("/")
    if not normalized:
        return ""
    first_segment, _, remainder = normalized.partition("/")
    if first_segment.lower() != MOBILE_FRONTEND_PREFIX:
        return normalized
    return remainder


def should_redirect_root_to_mobile(request: Request, settings: Settings) -> bool:
    if not settings.frontend_mobile_auto_redirect:
        return False
    if not mobile_frontend_available(settings):
        return False
    if _request_forces_desktop_view(request):
        return False
    return _request_prefers_mobile_view(request) or _is_probably_mobile_user_agent(request)


def should_redirect_mobile_path_to_desktop(request: Request) -> bool:
    return _request_forces_desktop_view(request)


def _replace_path(request: Request, next_path: str) -> str:
    url = request.url.replace(path=next_path)
    return str(url)


def build_mobile_redirect_response(request: Request) -> RedirectResponse:
    return RedirectResponse(url=_replace_path(request, f"/{MOBILE_FRONTEND_PREFIX}/"))


def build_desktop_redirect_response(request: Request, mobile_requested_path: str) -> RedirectResponse:
    stripped_path = strip_mobile_frontend_prefix(mobile_requested_path).strip("/")
    next_path = f"/{stripped_path}" if stripped_path else "/"
    return RedirectResponse(url=_replace_path(request, next_path))


def _serve_from_dist(dist_dir: Path, requested_path: str, *, label: str) -> Response:
    if not _dist_available(dist_dir):
        return _frontend_unavailable_response(dist_dir, label=label)

    candidate = _safe_candidate(dist_dir, requested_path)
    if candidate and candidate.exists() and candidate.is_file():
        media_type = mimetypes.guess_type(str(candidate))[0] or None
        return FileResponse(candidate, media_type=media_type)

    index_file = dist_dir / "index.html"
    if index_file.exists():
        media_type = mimetypes.guess_type(str(index_file))[0] or None
        return FileResponse(index_file, media_type=media_type)

    raise HTTPException(status_code=404, detail="Frontend asset not found")


def serve_frontend_asset(settings: Settings, requested_path: str) -> Response:
    return _serve_from_dist(settings.frontend_dist_dir, requested_path, label="Desktop")


def serve_frontend_app_asset(settings: Settings, requested_path: str) -> Response:
    mobile_dist_dir = settings.frontend_app_dist_dir or settings.frontend_dist_dir
    return _serve_from_dist(mobile_dist_dir, requested_path, label="Mobile")
