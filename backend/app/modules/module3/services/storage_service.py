from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.file_assets.service import register_file, resolve_file_for_owner

from ..core.database import database_enabled, init_database, session_scope
from ..core.config import DOCSETS_DIR, RUNS_DIR, STORAGE_DIR, TEMPLATES_DIR
from ..models.db_tables import DocsetFileTable, DocsetTable, RunLogTable, RunTable, TemplateTable


STATUS_WRITE_LOCK = threading.Lock()
RUN_WARNING_PREFIXES = (
    "[header inferred]",
    "[header unresolved]",
)
DEFAULT_OWNER_ID = "default"
OWNER_MODE_COMPAT_DEFAULT = "compat_default"
OWNER_MODE_STRICT_PREFERRED = "strict_preferred"
OWNER_MODE_STRICT_REQUIRED = "strict_required"
_OWNER_MODES = {
    OWNER_MODE_COMPAT_DEFAULT,
    OWNER_MODE_STRICT_PREFERRED,
    OWNER_MODE_STRICT_REQUIRED,
}
_OWNER_BACKFILL_LOCK = threading.Lock()
_OWNER_BACKFILL_DONE = False


def get_owner_mode() -> str:
    raw_value = str(os.getenv("MODULE3_OWNER_MODE", "") or "").strip().lower()
    if raw_value in _OWNER_MODES:
        return raw_value

    # Legacy switch compatibility:
    # MODULE3_OWNER_COMPAT_FALLBACK=0 means strict mode if MODULE3_OWNER_MODE is omitted.
    legacy_fallback_enabled = str(os.getenv("MODULE3_OWNER_COMPAT_FALLBACK", "0") or "").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    return OWNER_MODE_COMPAT_DEFAULT if legacy_fallback_enabled else OWNER_MODE_STRICT_REQUIRED


def _owner_backfill_on_boot_enabled() -> bool:
    raw_value = str(os.getenv("MODULE3_OWNER_BACKFILL_ON_BOOT", "1") or "").strip().lower()
    return raw_value not in {"0", "false", "off", "no"}


def normalize_owner_id(owner_id: Any) -> str:
    normalized = str(owner_id or "").strip()
    return normalized or DEFAULT_OWNER_ID


def _owner_matches(record_owner_id: Any, expected_owner_id: str | None) -> bool:
    if expected_owner_id is None:
        return True

    mode = get_owner_mode()
    expected = normalize_owner_id(expected_owner_id)
    raw_owner = str(record_owner_id or "").strip()
    if not raw_owner:
        return mode in {OWNER_MODE_COMPAT_DEFAULT, OWNER_MODE_STRICT_PREFERRED}

    actual = normalize_owner_id(raw_owner)
    if actual == expected:
        return True
    if mode == OWNER_MODE_COMPAT_DEFAULT and actual == DEFAULT_OWNER_ID:
        return True
    return False


def _resolve_record_owner(record: dict[str, Any], requested_owner_id: str | None = None) -> str:
    raw_owner = str(record.get("owner_id") or "").strip()
    if raw_owner:
        return normalize_owner_id(raw_owner)
    if requested_owner_id is not None:
        return normalize_owner_id(requested_owner_id)
    return DEFAULT_OWNER_ID


def _owner_backfill_candidates() -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(TEMPLATES_DIR.glob("*.json"))
    candidates.extend(DOCSETS_DIR.glob("*.json"))
    candidates.extend(RUNS_DIR.glob("*/status.json"))
    return candidates


def _backfill_owner_in_record(path: Path) -> None:
    try:
        payload = read_json(path)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    if str(payload.get("owner_id") or "").strip():
        return
    payload["owner_id"] = DEFAULT_OWNER_ID
    write_json_atomic(path, payload)


def _backfill_owner_metadata_once() -> None:
    global _OWNER_BACKFILL_DONE
    if _OWNER_BACKFILL_DONE:
        return
    if not _owner_backfill_on_boot_enabled():
        _OWNER_BACKFILL_DONE = True
        return
    with _OWNER_BACKFILL_LOCK:
        if _OWNER_BACKFILL_DONE:
            return
        for candidate in _owner_backfill_candidates():
            _backfill_owner_in_record(candidate)
        _OWNER_BACKFILL_DONE = True


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _template_record_from_entity(entity: TemplateTable) -> dict[str, Any]:
    return {
        "template_id": entity.template_id,
        "owner_id": normalize_owner_id(getattr(entity, "owner_id", "")),
        "filename": entity.filename,
        "path": entity.path,
        "template_file_id": entity.template_file_id,
        "sheet_name": entity.sheet_name,
        "header_row": entity.header_row,
        "write_row": entity.write_row,
        "table_index": entity.table_index,
        "template_type": entity.template_type,
        "fields": list(entity.fields_json or []),
        "tables": list(entity.tables_json or []),
        "created_at": _datetime_to_iso(entity.created_at),
    }


def _docset_record_from_entity(entity: DocsetTable) -> dict[str, Any]:
    files = [
        {
            "filename": item.filename,
            "path": item.path,
            "file_id": item.file_id,
        }
        for item in entity.files
    ]
    return {
        "doc_set_id": entity.doc_set_id,
        "owner_id": normalize_owner_id(getattr(entity, "owner_id", "")),
        "count": entity.count,
        "files": files,
        "created_at": _datetime_to_iso(entity.created_at),
    }


def _run_record_from_entity(entity: RunTable) -> dict[str, Any]:
    return {
        "run_id": entity.run_id,
        "owner_id": normalize_owner_id(getattr(entity, "owner_id", "")),
        "status": entity.status,
        "filled": entity.filled,
        "total": entity.total,
        "fill_rate": entity.fill_rate,
        "output_file_id": entity.output_file_id,
        "error": entity.error,
        "template_id": entity.template_id,
        "doc_set_id": entity.doc_set_id,
        "created_at": _datetime_to_iso(entity.created_at),
        "finished_at": _datetime_to_iso(entity.finished_at),
    }


def _sync_template_record(record: dict[str, Any]) -> None:
    if not database_enabled():
        return
    with session_scope() as session:
        entity = session.get(TemplateTable, record["template_id"])
        if entity is None:
            entity = TemplateTable(template_id=record["template_id"])
            owner_id = _resolve_record_owner(record)
        else:
            owner_id = normalize_owner_id(getattr(entity, "owner_id", "")) or _resolve_record_owner(record)
        entity.owner_id = owner_id
        record["owner_id"] = owner_id
        entity.filename = str(record["filename"])
        entity.path = str(record["path"])
        template_file_id = str(record.get("template_file_id") or "").strip()
        entity.template_file_id = template_file_id or None
        record["template_file_id"] = entity.template_file_id
        entity.sheet_name = record.get("sheet_name")
        entity.header_row = record.get("header_row")
        entity.write_row = record.get("write_row")
        entity.table_index = record.get("table_index")
        entity.template_type = str(record["template_type"])
        entity.fields_json = list(record.get("fields") or [])
        entity.tables_json = list(record.get("tables") or [])
        entity.created_at = _parse_datetime(record.get("created_at")) or datetime.utcnow()
        session.add(entity)


def _sync_docset_record(record: dict[str, Any]) -> None:
    if not database_enabled():
        return
    with session_scope() as session:
        entity = session.execute(
            select(DocsetTable)
            .options(selectinload(DocsetTable.files))
            .where(DocsetTable.doc_set_id == record["doc_set_id"])
        ).scalar_one_or_none()
        if entity is None:
            entity = DocsetTable(doc_set_id=record["doc_set_id"])
            owner_id = _resolve_record_owner(record)
        else:
            owner_id = normalize_owner_id(getattr(entity, "owner_id", "")) or _resolve_record_owner(record)
        entity.owner_id = owner_id
        record["owner_id"] = owner_id
        entity.count = int(record.get("count") or 0)
        entity.created_at = _parse_datetime(record.get("created_at")) or datetime.utcnow()
        entity.files.clear()
        for item in record.get("files") or []:
            file_id = str(item.get("file_id") or "").strip()
            path_value = str(item.get("path") or "").strip()
            if not path_value and file_id:
                try:
                    _, resolved_path = resolve_file_for_owner(file_id, owner_id)
                    path_value = str(resolved_path)
                    item["path"] = path_value
                except Exception:
                    path_value = ""
            entity.files.append(
                DocsetFileTable(
                    filename=str(item["filename"]),
                    path=path_value,
                    file_id=file_id or None,
                )
            )
            if file_id:
                item["file_id"] = file_id
        session.add(entity)


def _sync_run_record(record: dict[str, Any]) -> None:
    if not database_enabled():
        return
    with session_scope() as session:
        entity = session.get(RunTable, record["run_id"])
        if entity is None:
            entity = RunTable(run_id=record["run_id"])
            owner_id = _resolve_record_owner(record)
        else:
            owner_id = normalize_owner_id(getattr(entity, "owner_id", "")) or _resolve_record_owner(record)
        entity.owner_id = owner_id
        record["owner_id"] = owner_id
        entity.status = str(record.get("status") or "running")
        entity.filled = int(record.get("filled") or 0)
        entity.total = int(record.get("total") or 0)
        entity.fill_rate = float(record.get("fill_rate") or 0)
        entity.output_filename = None
        output_file_id = str(record.get("output_file_id") or "").strip()
        entity.output_file_id = output_file_id or None
        record["output_file_id"] = entity.output_file_id
        entity.error = record.get("error")
        entity.template_id = str(record.get("template_id") or "")
        entity.doc_set_id = str(record.get("doc_set_id") or "")
        entity.created_at = _parse_datetime(record.get("created_at")) or datetime.utcnow()
        entity.finished_at = _parse_datetime(record.get("finished_at"))
        session.add(entity)


def ensure_storage_dirs() -> None:
    for directory in (STORAGE_DIR, TEMPLATES_DIR, DOCSETS_DIR, RUNS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    _backfill_owner_metadata_once()
    if database_enabled():
        init_database()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def write_json_atomic(path: Path, payload: Any) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    last_error: Exception | None = None

    for _ in range(5):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(text, encoding="utf-8")
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1)

    if last_error is not None:
        raise last_error


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 文件损坏: {path}") from exc


def template_meta_path(template_id: str) -> Path:
    return TEMPLATES_DIR / f"{template_id}.json"


def docset_meta_path(doc_set_id: str) -> Path:
    return DOCSETS_DIR / f"{doc_set_id}.json"


def run_directory(run_id: str) -> Path:
    return RUNS_DIR / run_id


def run_status_path(run_id: str) -> Path:
    return run_directory(run_id) / "status.json"


def run_log_path(run_id: str) -> Path:
    return run_directory(run_id) / "run.log"


def run_rows_path(run_id: str) -> Path:
    return run_directory(run_id) / "rows.json"


def _load_run_warnings(run_id: str) -> list[str]:
    path = run_log_path(run_id)
    if not path.exists():
        return []

    warnings: list[str] = []
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                matched_prefix = next((prefix for prefix in RUN_WARNING_PREFIXES if prefix in line), None)
                if matched_prefix is None:
                    continue
                marker_index = line.find(matched_prefix)
                message = line[marker_index + len(matched_prefix) :].strip() if marker_index >= 0 else line
                if not message or message in seen:
                    continue
                seen.add(message)
                warnings.append(message)
    except OSError:
        return []
    return warnings


def _backfill_template_file_id(record: dict[str, Any]) -> bool:
    # New-track only: no legacy path backfill.
    return False


def _backfill_docset_file_ids(record: dict[str, Any]) -> bool:
    # New-track only: no legacy path backfill.
    return False


def _backfill_run_output_file_id(record: dict[str, Any]) -> bool:
    # New-track only: no legacy path backfill.
    return False


def save_template_record(record: dict[str, Any]) -> dict[str, Any]:
    record["owner_id"] = _resolve_record_owner(record)
    _backfill_template_file_id(record)
    _sync_template_record(record)
    write_json_atomic(template_meta_path(record["template_id"]), record)
    return record


def save_docset_record(record: dict[str, Any]) -> dict[str, Any]:
    record["owner_id"] = _resolve_record_owner(record)
    _backfill_docset_file_ids(record)
    _sync_docset_record(record)
    write_json_atomic(docset_meta_path(record["doc_set_id"]), record)
    return record


def create_run_record(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {"run_id": run_id, **payload}
    record["owner_id"] = _resolve_record_owner(record)
    _backfill_run_output_file_id(record)
    _sync_run_record(record)
    write_json_atomic(run_status_path(run_id), record)
    return record


def load_template_record(template_id: str, owner_id: str | None = None) -> dict[str, Any]:
    normalized_owner = normalize_owner_id(owner_id) if owner_id is not None else None
    if database_enabled():
        with session_scope() as session:
            entity = session.get(TemplateTable, template_id)
            if entity is not None:
                record = _template_record_from_entity(entity)
                if _owner_matches(record.get("owner_id"), normalized_owner):
                    if _backfill_template_file_id(record):
                        _sync_template_record(record)
                        write_json_atomic(template_meta_path(record["template_id"]), record)
                    return record
    path = template_meta_path(template_id)
    if not path.exists():
        raise FileNotFoundError(f"模板不存在: {template_id}")
    record = read_json(path)
    if not _owner_matches(record.get("owner_id"), normalized_owner):
        raise FileNotFoundError(f"template not found: {template_id}")
    previous_owner = str(record.get("owner_id") or "").strip()
    record["owner_id"] = _resolve_record_owner(record, normalized_owner)
    changed = previous_owner != str(record.get("owner_id") or "").strip()
    if _backfill_template_file_id(record):
        changed = True
    if database_enabled():
        _sync_template_record(record)
    if changed:
        write_json_atomic(template_meta_path(record["template_id"]), record)
    return record


def load_docset_record(doc_set_id: str, owner_id: str | None = None) -> dict[str, Any]:
    normalized_owner = normalize_owner_id(owner_id) if owner_id is not None else None
    if database_enabled():
        with session_scope() as session:
            entity = session.execute(
                select(DocsetTable)
                .options(selectinload(DocsetTable.files))
                .where(DocsetTable.doc_set_id == doc_set_id)
            ).scalar_one_or_none()
            if entity is not None:
                record = _docset_record_from_entity(entity)
                if _owner_matches(record.get("owner_id"), normalized_owner):
                    if _backfill_docset_file_ids(record):
                        _sync_docset_record(record)
                        write_json_atomic(docset_meta_path(record["doc_set_id"]), record)
                    return record
    path = docset_meta_path(doc_set_id)
    if not path.exists():
        raise FileNotFoundError(f"文档集不存在: {doc_set_id}")
    record = read_json(path)
    if not _owner_matches(record.get("owner_id"), normalized_owner):
        raise FileNotFoundError(f"docset not found: {doc_set_id}")
    previous_owner = str(record.get("owner_id") or "").strip()
    record["owner_id"] = _resolve_record_owner(record, normalized_owner)
    changed = previous_owner != str(record.get("owner_id") or "").strip()
    if _backfill_docset_file_ids(record):
        changed = True
    if database_enabled():
        _sync_docset_record(record)
    if changed:
        write_json_atomic(docset_meta_path(record["doc_set_id"]), record)
    return record


def load_run_record(run_id: str, owner_id: str | None = None) -> dict[str, Any]:
    normalized_owner = normalize_owner_id(owner_id) if owner_id is not None else None
    if database_enabled():
        with session_scope() as session:
            entity = session.get(RunTable, run_id)
            if entity is not None:
                record = _run_record_from_entity(entity)
                if not _owner_matches(record.get("owner_id"), normalized_owner):
                    raise FileNotFoundError(f"run not found: {run_id}")
                if _backfill_run_output_file_id(record):
                    _sync_run_record(record)
                    write_json_atomic(run_status_path(run_id), record)
                record["warnings"] = _load_run_warnings(run_id)
                return record
    path = run_status_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"任务不存在: {run_id}")
    record = read_json(path)
    if not _owner_matches(record.get("owner_id"), normalized_owner):
        raise FileNotFoundError(f"run not found: {run_id}")
    previous_owner = str(record.get("owner_id") or "").strip()
    record["owner_id"] = _resolve_record_owner(record, normalized_owner)
    changed = previous_owner != str(record.get("owner_id") or "").strip()
    if _backfill_run_output_file_id(record):
        changed = True
    record["warnings"] = _load_run_warnings(run_id)
    if database_enabled():
        _sync_run_record(record)
    if changed:
        write_json_atomic(run_status_path(run_id), record)
    return record


def append_run_log(run_id: str, message: str) -> None:
    if database_enabled():
        with session_scope() as session:
            session.add(RunLogTable(run_id=run_id, message=message.rstrip()))
    path = run_log_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(message.rstrip() + "\n")


def set_run_status(run_id: str, **updates: Any) -> dict[str, Any]:
    path = run_status_path(run_id)
    with STATUS_WRITE_LOCK:
        try:
            current = load_run_record(run_id)
        except FileNotFoundError:
            current = {"run_id": run_id}
        current.update(updates)
        _sync_run_record(current)
        write_json_atomic(path, current)
        return current


async def save_upload_file(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as fh:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
    await upload.close()


def register_template_file_asset(path: Path | str, owner_id: str, *, filename: str | None = None) -> str:
    asset = register_file(
        path=path,
        owner_id=normalize_owner_id(owner_id),
        source_module="module3",
        purpose="template",
        filename=filename,
    )
    return asset["file_id"]


def register_docset_file_asset(path: Path | str, owner_id: str, *, filename: str | None = None) -> str:
    asset = register_file(
        path=path,
        owner_id=normalize_owner_id(owner_id),
        source_module="module3",
        purpose="docset_source",
        filename=filename,
    )
    return asset["file_id"]


def register_run_output_file_asset(path: Path | str, owner_id: str, *, filename: str | None = None) -> str:
    asset = register_file(
        path=path,
        owner_id=normalize_owner_id(owner_id),
        source_module="module3",
        purpose="run_output",
        filename=filename,
    )
    return asset["file_id"]


__all__ = [
    "append_run_log",
    "create_run_record",
    "docset_meta_path",
    "ensure_storage_dirs",
    "get_owner_mode",
    "load_docset_record",
    "load_run_record",
    "load_template_record",
    "new_id",
    "normalize_owner_id",
    "read_json",
    "register_docset_file_asset",
    "register_run_output_file_asset",
    "register_template_file_asset",
    "run_directory",
    "run_log_path",
    "run_rows_path",
    "run_status_path",
    "save_docset_record",
    "save_upload_file",
    "save_template_record",
    "set_run_status",
    "template_meta_path",
    "unique_path",
    "utcnow_iso",
    "write_json_atomic",
]
