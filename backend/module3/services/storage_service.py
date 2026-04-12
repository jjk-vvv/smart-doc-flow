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

from ..core.database import database_enabled, init_database, session_scope
from ..core.config import DOCSETS_DIR, RUNS_DIR, STORAGE_DIR, TEMPLATES_DIR
from ..models.db_tables import DocsetFileTable, DocsetTable, RunLogTable, RunTable, TemplateTable


STATUS_WRITE_LOCK = threading.Lock()
RUN_WARNING_PREFIXES = (
    "[header inferred]",
    "[header unresolved]",
)


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
        "filename": entity.filename,
        "path": entity.path,
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
    files = [{"filename": item.filename, "path": item.path} for item in entity.files]
    return {
        "doc_set_id": entity.doc_set_id,
        "count": entity.count,
        "files": files,
        "created_at": _datetime_to_iso(entity.created_at),
    }


def _run_record_from_entity(entity: RunTable) -> dict[str, Any]:
    return {
        "run_id": entity.run_id,
        "status": entity.status,
        "filled": entity.filled,
        "total": entity.total,
        "fill_rate": entity.fill_rate,
        "output_filename": entity.output_filename,
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
        entity.filename = str(record["filename"])
        entity.path = str(record["path"])
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
        entity.count = int(record.get("count") or 0)
        entity.created_at = _parse_datetime(record.get("created_at")) or datetime.utcnow()
        entity.files.clear()
        for item in record.get("files") or []:
            entity.files.append(
                DocsetFileTable(
                    filename=str(item["filename"]),
                    path=str(item["path"]),
                )
            )
        session.add(entity)


def _sync_run_record(record: dict[str, Any]) -> None:
    if not database_enabled():
        return
    with session_scope() as session:
        entity = session.get(RunTable, record["run_id"])
        if entity is None:
            entity = RunTable(run_id=record["run_id"])
        entity.status = str(record.get("status") or "running")
        entity.filled = int(record.get("filled") or 0)
        entity.total = int(record.get("total") or 0)
        entity.fill_rate = float(record.get("fill_rate") or 0)
        entity.output_filename = record.get("output_filename")
        entity.error = record.get("error")
        entity.template_id = str(record.get("template_id") or "")
        entity.doc_set_id = str(record.get("doc_set_id") or "")
        entity.created_at = _parse_datetime(record.get("created_at")) or datetime.utcnow()
        entity.finished_at = _parse_datetime(record.get("finished_at"))
        session.add(entity)


def ensure_storage_dirs() -> None:
    for directory in (STORAGE_DIR, TEMPLATES_DIR, DOCSETS_DIR, RUNS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
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


def save_template_record(record: dict[str, Any]) -> dict[str, Any]:
    _sync_template_record(record)
    write_json_atomic(template_meta_path(record["template_id"]), record)
    return record


def save_docset_record(record: dict[str, Any]) -> dict[str, Any]:
    _sync_docset_record(record)
    write_json_atomic(docset_meta_path(record["doc_set_id"]), record)
    return record


def create_run_record(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {"run_id": run_id, **payload}
    _sync_run_record(record)
    write_json_atomic(run_status_path(run_id), record)
    return record


def load_template_record(template_id: str) -> dict[str, Any]:
    if database_enabled():
        with session_scope() as session:
            entity = session.get(TemplateTable, template_id)
            if entity is not None:
                return _template_record_from_entity(entity)
    path = template_meta_path(template_id)
    if not path.exists():
        raise FileNotFoundError(f"模板不存在: {template_id}")
    record = read_json(path)
    if database_enabled():
        _sync_template_record(record)
    return record


def load_docset_record(doc_set_id: str) -> dict[str, Any]:
    if database_enabled():
        with session_scope() as session:
            entity = session.execute(
                select(DocsetTable)
                .options(selectinload(DocsetTable.files))
                .where(DocsetTable.doc_set_id == doc_set_id)
            ).scalar_one_or_none()
            if entity is not None:
                return _docset_record_from_entity(entity)
    path = docset_meta_path(doc_set_id)
    if not path.exists():
        raise FileNotFoundError(f"文档集不存在: {doc_set_id}")
    record = read_json(path)
    if database_enabled():
        _sync_docset_record(record)
    return record


def load_run_record(run_id: str) -> dict[str, Any]:
    if database_enabled():
        with session_scope() as session:
            entity = session.get(RunTable, run_id)
            if entity is not None:
                record = _run_record_from_entity(entity)
                record["warnings"] = _load_run_warnings(run_id)
                return record
    path = run_status_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"任务不存在: {run_id}")
    record = read_json(path)
    record["warnings"] = _load_run_warnings(run_id)
    if database_enabled():
        _sync_run_record(record)
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


__all__ = [
    "append_run_log",
    "create_run_record",
    "docset_meta_path",
    "ensure_storage_dirs",
    "load_docset_record",
    "load_run_record",
    "load_template_record",
    "new_id",
    "read_json",
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
