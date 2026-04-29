from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

from app.core.paths import resolve_data_root_dir, resolve_runtime_root_dir

from .conversion_service import is_word_file


_INDEX_LOCK = threading.Lock()
_WORD_SUFFIXES = {".doc", ".docx"}


class OfficeOnlinePreviewError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, default) or "").strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _resolve_preview_root() -> Path:
    explicit = str(os.getenv("MODULE1_OFFICE_ONLINE_PREVIEW_ROOT_DIR", "") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    data_root = resolve_data_root_dir(resolve_runtime_root_dir())
    return (data_root / "module1" / "office-online-preview").resolve()


def _index_path() -> Path:
    return (_resolve_preview_root() / "index.json").resolve()


def _ensure_storage() -> None:
    root = _resolve_preview_root()
    root.mkdir(parents=True, exist_ok=True)
    index = _index_path()
    if not index.exists():
        _write_json_atomic(index, {"version": 1, "items": {}})


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_index() -> dict[str, Any]:
    _ensure_storage()
    try:
        payload = json.loads(_index_path().read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": 1, "items": {}}
    if not isinstance(payload, dict):
        payload = {"version": 1, "items": {}}
    if not isinstance(payload.get("items"), dict):
        payload["items"] = {}
    payload.setdefault("version", 1)
    return payload


def _save_index(payload: dict[str, Any]) -> None:
    _write_json_atomic(_index_path(), payload)


def _safe_filename(value: str, suffix: str) -> str:
    raw = str(value or "").strip() or f"document{suffix}"
    cleaned = "".join("_" if ch in '<>:"/\\|?*\x00' else ch for ch in raw).strip(" .")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        cleaned = f"document{suffix}"
    if suffix and not cleaned.lower().endswith(suffix):
        cleaned = f"{Path(cleaned).stem or 'document'}{suffix}"
    return cleaned[:180]


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8", "ignore")).hexdigest()


def _parse_expires_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_expired(record: dict[str, Any]) -> bool:
    expires_at = _parse_expires_at(str(record.get("expires_at") or ""))
    return expires_at is None or expires_at <= _utcnow()


def _cleanup_expired_locked(index_payload: dict[str, Any]) -> None:
    items = index_payload.get("items")
    if not isinstance(items, dict):
        index_payload["items"] = {}
        return
    expired_keys = [
        key
        for key, value in items.items()
        if not isinstance(value, dict) or _is_expired(value)
    ]
    for key in expired_keys:
        items.pop(key, None)


def _guess_mime(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".doc":
        return "application/msword"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _configured_public_base_url() -> str:
    for name in (
        "MODULE1_OFFICE_ONLINE_PUBLIC_BASE_URL",
        "SMART_DOC_FLOW_PUBLIC_BASE_URL",
        "APP_PUBLIC_BASE_URL",
        "GATEWAY_PUBLIC_BASE_URL",
    ):
        value = str(os.getenv(name, "") or "").strip().rstrip("/")
        if value:
            return value
    return ""


def _request_public_base_url(request: Request) -> tuple[str, str]:
    configured = _configured_public_base_url()
    if configured:
        return configured, ""

    headers = request.headers
    proto = str(headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = str(headers.get("x-forwarded-host") or headers.get("host") or "").split(",")[0].strip()
    if host:
        base = f"{proto}://{host}".rstrip("/")
    else:
        base = str(request.base_url).rstrip("/")

    lowered = base.lower()
    if "localhost" in lowered or "127.0.0.1" in lowered or "[::1]" in lowered:
        return base, "当前根据请求推导出的预览公网地址是本地地址，Microsoft Office 在线预览可能无法访问。建议配置 MODULE1_OFFICE_ONLINE_PUBLIC_BASE_URL。"
    return base, ""


def _build_source_url(base_url: str, token: str, filename: str) -> str:
    encoded_token = urllib.parse.quote(token, safe="")
    encoded_filename = urllib.parse.quote(filename, safe="")
    return f"{base_url.rstrip('/')}/module1/office-online/preview/public/{encoded_token}/{encoded_filename}"


def _build_iframe_url(source_url: str) -> str:
    return "https://view.officeapps.live.com/op/embed.aspx?src=" + urllib.parse.quote(source_url, safe="")


def create_office_online_preview(
    *,
    request: Request,
    owner_id: str,
    file_name: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    normalized_owner = str(owner_id or "").strip()
    if not normalized_owner:
        raise OfficeOnlinePreviewError("authenticated owner is required", status_code=401)

    original_name = str(file_name or "").strip()
    if not original_name:
        raise OfficeOnlinePreviewError("empty file name")
    if not is_word_file(original_name):
        raise OfficeOnlinePreviewError("Only .doc/.docx files can be previewed with Office Online")
    if not file_bytes:
        raise OfficeOnlinePreviewError("empty office payload")

    suffix = Path(original_name).suffix.lower()
    if suffix not in _WORD_SUFFIXES:
        raise OfficeOnlinePreviewError("Only .doc/.docx files can be previewed with Office Online")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    safe_name = _safe_filename(original_name, suffix)
    storage_dir = (_resolve_preview_root() / "files" / normalized_owner[:32] / file_hash[:2] / file_hash).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = (storage_dir / safe_name).resolve()
    if not file_path.exists() or file_path.read_bytes() != file_bytes:
        file_path.write_bytes(file_bytes)

    ttl_minutes = max(5, min(_env_int("MODULE1_OFFICE_ONLINE_PREVIEW_TTL_MINUTES", 30), 1440))
    expires_at = _utcnow() + timedelta(minutes=ttl_minutes)
    token = f"opv_{secrets.token_urlsafe(32)}"
    token_hash = _token_hash(token)
    base_url, warning = _request_public_base_url(request)
    source_url = _build_source_url(base_url, token, safe_name)
    iframe_url = _build_iframe_url(source_url)
    now = _utcnow_iso()
    record = {
        "token_hash": token_hash,
        "owner_id": normalized_owner,
        "file_hash": file_hash,
        "path": str(file_path),
        "filename": safe_name,
        "mime_type": _guess_mime(safe_name),
        "size_bytes": len(file_bytes),
        "source_module": "module1",
        "purpose": "office-online-preview",
        "created_at": now,
        "updated_at": now,
        "expires_at": expires_at.isoformat(),
        "public_base_url": base_url,
    }

    with _INDEX_LOCK:
        index_payload = _load_index()
        _cleanup_expired_locked(index_payload)
        index_payload["items"][token_hash] = record
        _save_index(index_payload)

    return {
        "ok": True,
        "mode": "office_online",
        "source_url": source_url,
        "iframe_url": iframe_url,
        "file_name": safe_name,
        "mime_type": record["mime_type"],
        "size_bytes": len(file_bytes),
        "expires_at": record["expires_at"],
        "public_base_url": base_url,
        "public_url_warning": warning,
    }


def resolve_office_online_preview_file(token: str) -> tuple[Path, dict[str, Any]]:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        raise OfficeOnlinePreviewError("missing preview token", status_code=404)

    token_hash = _token_hash(normalized_token)
    with _INDEX_LOCK:
        index_payload = _load_index()
        raw = index_payload.get("items", {}).get(token_hash)
        if not isinstance(raw, dict):
            raise OfficeOnlinePreviewError("preview token not found", status_code=404)
        if _is_expired(raw):
            index_payload.get("items", {}).pop(token_hash, None)
            _save_index(index_payload)
            raise OfficeOnlinePreviewError("preview token expired", status_code=410)
        raw["last_accessed_at"] = _utcnow_iso()
        raw["access_count"] = int(raw.get("access_count") or 0) + 1
        index_payload["items"][token_hash] = raw
        _save_index(index_payload)
        record = dict(raw)

    file_path = Path(str(record.get("path") or "")).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise OfficeOnlinePreviewError("preview source file missing", status_code=404)
    return file_path, record


__all__ = [
    "OfficeOnlinePreviewError",
    "create_office_online_preview",
    "resolve_office_online_preview_file",
]
