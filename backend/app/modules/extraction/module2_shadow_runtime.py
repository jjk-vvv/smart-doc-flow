from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, UploadFile, status
from requests import RequestException

from app.core.config import Settings

from .config import get_extraction_settings


ParseSchemaFormFn = Callable[[str], dict[str, Any]]
ReadUploadsForUpstreamFn = Callable[[list[UploadFile]], Awaitable[list[tuple[str, tuple[str, bytes, str]]]]]
ExecutionFacadeFactory = Callable[[], Any]


@dataclass
class ExtractionShadowJob:
    job_id: str
    status: str
    terminal: bool
    updated_at: float
    payload: dict[str, Any]


extraction_shadow_jobs: dict[str, ExtractionShadowJob] = {}
extraction_shadow_pollers: dict[str, threading.Thread] = {}
extraction_shadow_lock = threading.RLock()
extraction_shadow_snapshot_lock = threading.Lock()
extraction_shadow_generation = 0
SHADOW_SNAPSHOT_REPLACE_RETRIES = 8
SHADOW_SNAPSHOT_RETRY_DELAY_SEC = 0.06


async def start_shadow_extraction_job(
    settings: Settings,
    uploads: list[UploadFile],
    schema_form: str,
    *,
    parse_schema_form_json: ParseSchemaFormFn,
    read_uploads_for_upstream: ReadUploadsForUpstreamFn,
    execution_facade_factory: ExecutionFacadeFactory,
    tenant_id: str = "",
) -> dict[str, Any]:
    if not uploads:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(uploads) > 5:
        raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

    parse_schema_form_json(schema_form)
    files_payload = await read_uploads_for_upstream(uploads)
    payload = await execution_facade_factory().create_job(
        settings,
        files_payload=files_payload,
        schema_form=schema_form,
        tenant_id=tenant_id,
    )
    job_id = _extract_job_id(payload)
    _upsert_shadow_payload(settings, payload)
    if not bool(payload.get("terminal")):
        _ensure_shadow_poller(settings, job_id, execution_facade_factory=execution_facade_factory)
    return payload


def get_shadow_extraction_job_status(
    settings: Settings,
    job_id: str,
    *,
    execution_facade_factory: ExecutionFacadeFactory,
    include_documents: bool = False,
    expected_tenant_id: str = "",
) -> dict[str, Any]:
    normalized_job_id = _normalize_job_id(job_id)
    if not normalized_job_id:
        raise HTTPException(status_code=404, detail="Extraction job not found")

    _cleanup_shadow_jobs(settings)
    snapshot_payload = _enforce_shadow_payload_tenant(
        _get_shadow_payload(settings, normalized_job_id),
        expected_tenant_id,
    )
    try:
        payload = execution_facade_factory().get_job_status(
            settings,
            job_id=normalized_job_id,
            include_documents=include_documents,
        )
        payload = _enforce_shadow_payload_tenant(payload, expected_tenant_id) or payload
        _upsert_shadow_payload(settings, payload)
        if not bool(payload.get("terminal")):
            _ensure_shadow_poller(settings, normalized_job_id, execution_facade_factory=execution_facade_factory)
        return payload
    except HTTPException as exc:
        if exc.status_code == 404 and snapshot_payload and bool(snapshot_payload.get("terminal")):
            return snapshot_payload
        raise
    except RequestException as exc:
        if snapshot_payload:
            return snapshot_payload
        raise HTTPException(status_code=502, detail=f"Module2 upstream unavailable: {type(exc).__name__}: {exc}") from exc


def cancel_shadow_extraction_job_file(
    settings: Settings,
    job_id: str,
    *,
    file_hash: str,
    file_name: str = "",
    execution_facade_factory: ExecutionFacadeFactory,
    expected_tenant_id: str = "",
) -> dict[str, Any]:
    normalized_job_id = _normalize_job_id(job_id)
    normalized_hash = str(file_hash or "").strip()
    normalized_name = str(file_name or "").strip()
    if not normalized_job_id:
        raise HTTPException(status_code=404, detail="Extraction job not found")
    if not normalized_hash and not normalized_name:
        raise HTTPException(status_code=400, detail="file_hash or file_name is required")

    _cleanup_shadow_jobs(settings)
    _enforce_shadow_payload_tenant(_get_shadow_payload(settings, normalized_job_id), expected_tenant_id)
    result = execution_facade_factory().cancel_job_file(
        settings,
        job_id=normalized_job_id,
        file_hash=normalized_hash,
        file_name=normalized_name,
    )

    try:
        refreshed_payload = execution_facade_factory().get_job_status(
            settings,
            job_id=normalized_job_id,
            include_documents=False,
        )
    except Exception:
        refreshed_payload = None

    if isinstance(refreshed_payload, dict) and refreshed_payload:
        refreshed_payload = _enforce_shadow_payload_tenant(refreshed_payload, expected_tenant_id) or refreshed_payload
        _upsert_shadow_payload(settings, refreshed_payload)
        if not bool(refreshed_payload.get("terminal")):
            _ensure_shadow_poller(settings, normalized_job_id, execution_facade_factory=execution_facade_factory)
    return result


def clear_shadow_extraction_runtime_state(
    settings: Settings,
    *,
    remove_snapshots: bool,
) -> dict[str, int]:
    global extraction_shadow_generation

    with extraction_shadow_lock:
        extraction_shadow_generation += 1
        cleared_jobs = len(extraction_shadow_jobs)
        cleared_pollers = len(extraction_shadow_pollers)
        extraction_shadow_jobs.clear()
        extraction_shadow_pollers.clear()

    removed_snapshots = 0
    if remove_snapshots:
        try:
            for path in _shadow_job_root_dir(settings).glob("*.json"):
                try:
                    path.unlink(missing_ok=True)
                    removed_snapshots += 1
                except Exception:
                    continue
        except Exception:
            removed_snapshots = 0

    return {
        "cleared_shadow_jobs_memory": int(cleared_jobs),
        "cleared_shadow_pollers_memory": int(cleared_pollers),
        "removed_shadow_snapshots": int(removed_snapshots),
    }


def _ensure_shadow_poller(
    settings: Settings,
    job_id: str,
    *,
    execution_facade_factory: ExecutionFacadeFactory,
) -> None:
    normalized_job_id = _normalize_job_id(job_id)
    if not normalized_job_id:
        return
    with extraction_shadow_lock:
        generation = extraction_shadow_generation
        existing = extraction_shadow_pollers.get(normalized_job_id)
        if existing and existing.is_alive():
            return
        worker = threading.Thread(
            target=_run_shadow_poller,
            args=(settings, normalized_job_id, generation, execution_facade_factory),
            name=f"extract-shadow-{normalized_job_id[:12]}",
            daemon=True,
        )
        extraction_shadow_pollers[normalized_job_id] = worker
    worker.start()


def _run_shadow_poller(
    settings: Settings,
    job_id: str,
    generation: int,
    execution_facade_factory: ExecutionFacadeFactory,
) -> None:
    extraction_settings = get_extraction_settings()
    timeout_sec = extraction_settings.shadow_poll_timeout_sec
    interval_sec = extraction_settings.shadow_poll_interval_sec
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline:
            if not _shadow_generation_matches(generation):
                return
            snapshot_payload = _get_shadow_payload(settings, job_id)
            if snapshot_payload and bool(snapshot_payload.get("terminal")):
                return
            try:
                payload = execution_facade_factory().get_job_status(settings, job_id=job_id)
                if not _shadow_generation_matches(generation):
                    return
                _upsert_shadow_payload(settings, payload, expected_generation=generation)
                if bool(payload.get("terminal")):
                    if "documents" not in payload:
                        try:
                            final_payload = execution_facade_factory().get_job_status(
                                settings,
                                job_id=job_id,
                                include_documents=True,
                            )
                            if not _shadow_generation_matches(generation):
                                return
                            _upsert_shadow_payload(settings, final_payload, expected_generation=generation)
                        except Exception:
                            pass
                    return
            except Exception:
                pass
            time.sleep(interval_sec)
    finally:
        with extraction_shadow_lock:
            existing = extraction_shadow_pollers.get(job_id)
            if existing and existing.ident == threading.get_ident():
                extraction_shadow_pollers.pop(job_id, None)


def _extract_job_id(payload: dict[str, Any]) -> str:
    job_id = _normalize_job_id(payload.get("job_id"))
    if not job_id:
        raise HTTPException(status_code=502, detail="Module2 upstream did not return a valid extraction job id")
    return job_id


def _normalize_job_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if not re.fullmatch(r"extract_job_[A-Za-z0-9]+", normalized):
        return normalized
    return normalized


def _normalize_tenant_id(value: Any) -> str:
    return str(value or "").strip()


def _extract_payload_tenant_id(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    tenant_id = _normalize_tenant_id(payload.get("tenant_id"))
    if tenant_id:
        return tenant_id
    runtime_spec = payload.get("runtime_spec")
    if isinstance(runtime_spec, dict):
        return _normalize_tenant_id(runtime_spec.get("tenant_id"))
    return ""


def _tenant_guard_mode() -> str:
    mode = str(get_extraction_settings().job_tenant_guard_mode or "").strip().lower()
    if mode in {"compat", "warn", "strict"}:
        return mode
    return "warn"


def _append_tenant_guard_warning(payload: dict[str, Any], warning: str) -> dict[str, Any]:
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        warning_list = [str(item) for item in warnings]
    else:
        warning_list = []
    if warning not in warning_list:
        warning_list.append(warning)
    cloned_payload = dict(payload)
    cloned_payload["warnings"] = warning_list
    return cloned_payload


def _enforce_shadow_payload_tenant(payload: dict[str, Any] | None, expected_tenant_id: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return payload

    normalized_expected = _normalize_tenant_id(expected_tenant_id)
    if not normalized_expected:
        return payload

    actual_tenant_id = _extract_payload_tenant_id(payload)
    mode = _tenant_guard_mode()
    if not actual_tenant_id:
        if mode == "strict":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Legacy extraction job is missing tenant binding in strict guard mode",
            )
        if mode == "warn":
            return _append_tenant_guard_warning(
                payload,
                "legacy extraction job payload missing tenant_id; compatibility path used",
            )
        return payload

    if actual_tenant_id != normalized_expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Extraction job does not belong to current tenant",
        )
    return payload


def _shadow_job_root_dir(settings: Settings) -> Path:
    root = (settings.data_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _shadow_job_state_path(settings: Settings, job_id: str) -> Path:
    safe_job_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(job_id or "").strip()) or "extract_job"
    return _shadow_job_root_dir(settings) / f"{safe_job_id}.json"


def _read_shadow_snapshot_text(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _write_json_file_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}-{threading.get_ident()}")

    with extraction_shadow_snapshot_lock:
        if _read_shadow_snapshot_text(path) == serialized:
            return

        temp_path.write_text(serialized, encoding="utf-8")
        try:
            last_error: PermissionError | None = None
            for attempt in range(SHADOW_SNAPSHOT_REPLACE_RETRIES):
                try:
                    temp_path.replace(path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    if _read_shadow_snapshot_text(path) == serialized:
                        return
                    if attempt + 1 < SHADOW_SNAPSHOT_REPLACE_RETRIES:
                        time.sleep(SHADOW_SNAPSHOT_RETRY_DELAY_SEC)
                        continue

            if last_error is None:
                return

            for attempt in range(SHADOW_SNAPSHOT_REPLACE_RETRIES):
                try:
                    path.write_text(serialized, encoding="utf-8")
                    return
                except PermissionError as exc:
                    last_error = exc
                    if _read_shadow_snapshot_text(path) == serialized:
                        return
                    if attempt + 1 < SHADOW_SNAPSHOT_REPLACE_RETRIES:
                        time.sleep(SHADOW_SNAPSHOT_RETRY_DELAY_SEC)
                        continue
                    raise
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _save_shadow_snapshot(settings: Settings, job_id: str, payload: dict[str, Any]) -> None:
    snapshot_payload = {
        "version": 1,
        "saved_at": time.time(),
        "payload": payload,
    }
    _write_json_file_atomic(_shadow_job_state_path(settings, job_id), snapshot_payload)


def _load_shadow_snapshot(settings: Settings, job_id: str) -> dict[str, Any] | None:
    path = _shadow_job_state_path(settings, job_id)
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = payload.get("payload") if isinstance(payload, dict) else None
    return dict(result) if isinstance(result, dict) else None


def _upsert_shadow_payload(
    settings: Settings,
    payload: dict[str, Any],
    *,
    expected_generation: int | None = None,
) -> bool:
    if expected_generation is not None and not _shadow_generation_matches(expected_generation):
        return False
    job_id = _extract_job_id(payload)
    terminal = bool(payload.get("terminal"))
    updated_at = float(payload.get("updated_at", time.time()) or time.time())
    shadow_job = ExtractionShadowJob(
        job_id=job_id,
        status=str(payload.get("status") or "queued").strip() or "queued",
        terminal=terminal,
        updated_at=updated_at,
        payload=dict(payload),
    )
    with extraction_shadow_lock:
        if expected_generation is not None and not _shadow_generation_matches(expected_generation):
            return False
        existing = extraction_shadow_jobs.get(job_id)
        if existing is not None and existing.payload == shadow_job.payload:
            return True
        extraction_shadow_jobs[job_id] = shadow_job
    if expected_generation is not None and not _shadow_generation_matches(expected_generation):
        return False
    _save_shadow_snapshot(settings, job_id, shadow_job.payload)
    return True


def _get_shadow_payload(settings: Settings, job_id: str) -> dict[str, Any] | None:
    normalized_job_id = _normalize_job_id(job_id)
    if not normalized_job_id:
        return None
    with extraction_shadow_lock:
        existing = extraction_shadow_jobs.get(normalized_job_id)
        if existing is not None:
            return dict(existing.payload)
    payload = _load_shadow_snapshot(settings, normalized_job_id)
    if payload is not None:
        _upsert_shadow_payload(settings, payload)
    return payload


def _shadow_job_ttl_sec() -> float:
    return get_extraction_settings().extract_job_ttl_sec


def _shadow_job_cap() -> int:
    return get_extraction_settings().extract_job_cap


def _cleanup_shadow_jobs(settings: Settings) -> None:
    ttl_sec = _shadow_job_ttl_sec()
    cap = _shadow_job_cap()
    now_ts = time.time()
    removed_job_ids: list[str] = []
    with extraction_shadow_lock:
        stale = [
            job_id
            for job_id, job in extraction_shadow_jobs.items()
            if job.terminal and (now_ts - float(job.updated_at or 0.0)) > ttl_sec
        ]
        for job_id in stale:
            extraction_shadow_jobs.pop(job_id, None)
            removed_job_ids.append(job_id)
        if len(extraction_shadow_jobs) > cap:
            ordered_terminal = sorted(
                [job for job in extraction_shadow_jobs.values() if job.terminal],
                key=lambda item: float(item.updated_at or 0.0),
            )
            removable = max(0, len(extraction_shadow_jobs) - cap)
            for item in ordered_terminal[:removable]:
                extraction_shadow_jobs.pop(item.job_id, None)
                removed_job_ids.append(item.job_id)
    for job_id in removed_job_ids:
        try:
            _shadow_job_state_path(settings, job_id).unlink(missing_ok=True)
        except Exception:
            pass


def _shadow_generation_matches(generation: int) -> bool:
    with extraction_shadow_lock:
        return int(extraction_shadow_generation) == int(generation)
