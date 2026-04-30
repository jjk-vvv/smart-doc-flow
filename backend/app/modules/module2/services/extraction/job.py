from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


StateRootFactory = Callable[[], Path]
SafeArtifactPathFn = Callable[[str], Path]
LoadedFileEntry = Tuple[str, bytes, str, str, str, str]
JobStateFactory = Callable[..., Any]
JobFileStateFactory = Callable[..., Any]
DocumentValidateFn = Callable[[Any], Any]
RunExtractionJobFn = Callable[..., Awaitable[None]]
TaskFactory = Callable[[Awaitable[Any]], asyncio.Task[Any]]
PersistSnapshotFn = Callable[[str, bool], Awaitable[None]]

TERMINAL_FILE_STATUSES = {"completed", "failed", "cancelled"}
SKIPPABLE_FILE_STATUSES = TERMINAL_FILE_STATUSES | {"cancel_requested"}


def _sanitize_error_message(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    normalized = text.lower()
    if (
        normalized.startswith("<!doctype")
        or normalized.startswith("<html")
        or "<title>not found</title>" in normalized
        or (
            "server is powered by" in normalized
            and "frp" in normalized
        )
    ):
        return "模块二请求没有到达文档解析后端。请检查桌面端 API 地址、内网穿透或网关路由配置。"
    return text


def _sanitize_error_list(errors: Any) -> List[str]:
    raw_items = errors if isinstance(errors, list) else [errors]
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        message = _sanitize_error_message(item)
        if not message or message in seen:
            continue
        seen.add(message)
        cleaned.append(message)
    return cleaned


@dataclass
class ExtractionJobFileState:
    file_name: str
    file_hash: str
    status: str
    stage: str
    progress_ratio: float
    message: str
    artifact_path: Optional[str] = None
    artifact_url: Optional[str] = None
    error: str = ""
    track: str = ""
    cached: bool = False


@dataclass
class ExtractionJobState:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    total_files: int
    completed_files: int
    failed_files: int
    current_file_index: int
    current_file_name: str
    current_stage: str
    files: List[ExtractionJobFileState]
    documents: List[Any]
    errors: List[str]

    def terminal(self) -> bool:
        return self.status in {"completed", "failed"}


class ExtractionJobRuntime:
    def __init__(
        self,
        *,
        state_root_factory: StateRootFactory,
        safe_artifact_path: SafeArtifactPathFn,
        job_state_factory: JobStateFactory,
        job_file_state_factory: JobFileStateFactory,
        document_validate: DocumentValidateFn,
        run_extraction_job: RunExtractionJobFn,
        logger: Any,
        task_factory: TaskFactory | None = None,
    ) -> None:
        self._state_root_factory = state_root_factory
        self._safe_artifact_path = safe_artifact_path
        self._job_state_factory = job_state_factory
        self._job_file_state_factory = job_file_state_factory
        self._document_validate = document_validate
        self._run_extraction_job = run_extraction_job
        self._logger = logger
        self._task_factory = task_factory or asyncio.create_task

        self.jobs: Dict[str, Any] = {}
        self.lock = asyncio.Lock()
        self.runtime_specs: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, asyncio.Task[Any]] = {}
        self.persist_markers: Dict[str, float] = {}

    def serialize_job(self, job: Any, *, include_documents: bool = False) -> Dict[str, Any]:
        runtime_spec = self.runtime_specs.get(str(getattr(job, "job_id", "") or "").strip()) or {}
        total_files = max(1, int(job.total_files or 0))
        serialized_files: List[Dict[str, Any]] = []
        file_progress_values: List[float] = []
        queued_files = 0
        running_files: List[Dict[str, Any]] = []
        active_stages: Dict[str, int] = {}

        for idx, item in enumerate(job.files):
            raw_ratio = max(0.0, min(1.0, float(item.progress_ratio or 0.0)))
            file_progress_values.append(raw_ratio)
            status = str(item.status or "").strip().lower() or "queued"
            stage = str(item.stage or "").strip() or "queued"
            if status == "queued":
                queued_files += 1
            elif status not in TERMINAL_FILE_STATUSES:
                running_files.append(
                    {
                        "file_index": idx + 1,
                        "file_name": item.file_name,
                        "stage": stage,
                        "status": status,
                        "progress_ratio": round(raw_ratio, 4),
                    }
                )
                active_stages[stage] = int(active_stages.get(stage, 0)) + 1
            serialized_files.append(
                {
                    "file_name": item.file_name,
                    "file_hash": item.file_hash,
                    "status": item.status,
                    "stage": item.stage,
                    "progress_ratio": round(raw_ratio, 4),
                    "message": item.message,
                    "artifact_path": item.artifact_path,
                    "artifact_url": item.artifact_url,
                    "error": item.error,
                    "track": item.track,
                    "cached": bool(item.cached),
                }
            )

        progress_ratio = (sum(file_progress_values) / float(total_files)) if file_progress_values else 0.0
        current_file_index = int(job.current_file_index or 0)
        current_file_name = job.current_file_name
        current_stage = job.current_stage
        if running_files:
            preferred_running = next(
                (
                    item
                    for item in running_files
                    if int(item.get("file_index", 0) or 0) == current_file_index
                    and str(item.get("file_name", "")).strip() == str(current_file_name or "").strip()
                ),
                None,
            )
            active_item = preferred_running or running_files[0]
            current_file_index = int(active_item.get("file_index", 0) or current_file_index)
            current_file_name = str(active_item.get("file_name", current_file_name) or "")
            current_stage = str(active_item.get("stage", current_stage) or "")
        payload: Dict[str, Any] = {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "terminal": job.terminal(),
            "tenant_id": str(runtime_spec.get("tenant_id") or "").strip(),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "progress": {
                "total_files": int(job.total_files),
                "completed_files": int(job.completed_files),
                "failed_files": int(job.failed_files),
                "current_file_index": current_file_index,
                "current_file_name": current_file_name,
                "current_stage": current_stage,
                "progress_ratio": round(progress_ratio, 4),
                "queued_files": int(queued_files),
                "running_files": running_files,
                "active_stages": active_stages,
                "parallel_workers": len(running_files),
            },
            "files": serialized_files,
            "errors": list(job.errors),
        }
        if include_documents or job.terminal():
            ordered_documents: List[Any] = []
            bucketed_documents: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
            for doc in job.documents:
                key = (
                    str(getattr(doc, "file_hash", "") or ""),
                    str(getattr(doc, "file_name", "") or "").strip().lower(),
                )
                bucketed_documents[key].append(doc)
            for item in job.files:
                key = (str(item.file_hash or ""), str(item.file_name or "").strip().lower())
                bucket = bucketed_documents.get(key) or []
                if bucket:
                    ordered_documents.append(bucket.pop(0))
            for bucket in bucketed_documents.values():
                ordered_documents.extend(bucket)
            payload["documents"] = [doc.model_dump(mode="json") for doc in ordered_documents]
        return payload

    def state_path(self, job_id: str) -> Path:
        safe_job_id = re.sub(r"[^A-Za-z0-9._-]+", "_", str(job_id or "").strip()) or "extract_job"
        return self._state_root_factory() / f"{safe_job_id}.json"

    def _write_json_file_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def serialize_runtime_spec(self, job_id: str) -> Dict[str, Any]:
        spec = self.runtime_specs.get(str(job_id).strip()) or {}
        loaded_files = []
        for item in spec.get("loaded_files", []):
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("file_name") or "").strip()
            file_hash = str(item.get("file_hash") or "").strip()
            artifact_path = str(item.get("artifact_path") or "").strip()
            artifact_url = str(item.get("artifact_url") or "").strip()
            mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
            if not file_name or not file_hash or not artifact_path:
                continue
            loaded_files.append(
                {
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "artifact_path": artifact_path,
                    "artifact_url": artifact_url,
                    "mime_type": mime_type,
                }
            )
        return {
            "schema": spec.get("schema") if isinstance(spec.get("schema"), dict) else {},
            "schema_digest": str(spec.get("schema_digest") or "").strip(),
            "max_retries": max(0, int(spec.get("max_retries") or 0)),
            "tenant_id": str(spec.get("tenant_id") or "").strip(),
            "loaded_files": loaded_files,
        }

    def normalize_runtime_spec(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
        schema_digest = str(payload.get("schema_digest") or "").strip()
        max_retries = max(0, int(payload.get("max_retries") or 0))
        tenant_id = str(payload.get("tenant_id") or "").strip()
        loaded_files: List[Dict[str, str]] = []
        for item in payload.get("loaded_files", []):
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("file_name") or "").strip()
            file_hash = str(item.get("file_hash") or "").strip()
            artifact_path = str(item.get("artifact_path") or "").strip()
            artifact_url = str(item.get("artifact_url") or "").strip()
            mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
            if not file_name or not file_hash or not artifact_path:
                continue
            loaded_files.append(
                {
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "artifact_path": artifact_path,
                    "artifact_url": artifact_url,
                    "mime_type": mime_type,
                }
            )
        return {
            "schema": schema,
            "schema_digest": schema_digest,
            "max_retries": max_retries,
            "tenant_id": tenant_id,
            "loaded_files": loaded_files,
        }

    def build_runtime_spec(
        self,
        *,
        loaded_files: List[LoadedFileEntry],
        schema_obj: Dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> Dict[str, Any]:
        return {
            "schema": schema_obj,
            "schema_digest": schema_digest,
            "max_retries": max_retries,
            "tenant_id": tenant_id,
            "loaded_files": [
                {
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "artifact_path": artifact_path,
                    "artifact_url": artifact_url,
                    "mime_type": mime_type,
                }
                for file_name, _file_bytes, file_hash, artifact_path, artifact_url, mime_type in loaded_files
            ],
        }

    def build_queued_job_state(
        self,
        *,
        job_id: str,
        loaded_files: List[LoadedFileEntry],
    ) -> Any:
        now_ts = time.time()
        return self._job_state_factory(
            job_id=job_id,
            status="queued",
            created_at=now_ts,
            updated_at=now_ts,
            total_files=len(loaded_files),
            completed_files=0,
            failed_files=0,
            current_file_index=0,
            current_file_name="",
            current_stage="queued",
            files=[
                self._job_file_state_factory(
                    file_name=file_name,
                    file_hash=file_hash,
                    status="queued",
                    stage="queued",
                    progress_ratio=0.0,
                    message="等待开始解析",
                    artifact_path=artifact_path,
                    artifact_url=artifact_url,
                )
                for file_name, _file_bytes, file_hash, artifact_path, artifact_url, _mime_type in loaded_files
            ],
            documents=[],
            errors=[],
        )

    async def register_job(
        self,
        *,
        loaded_files: List[LoadedFileEntry],
        schema_obj: Dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> Any:
        job_id = f"extract_job_{uuid.uuid4().hex[:16]}"
        job_state = self.build_queued_job_state(job_id=job_id, loaded_files=loaded_files)
        runtime_spec = self.build_runtime_spec(
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=tenant_id,
        )
        async with self.lock:
            self.cleanup_jobs_locked()
            self.jobs[job_id] = job_state
            self.runtime_specs[job_id] = runtime_spec
        await self.persist_snapshot(job_id, True)
        self.schedule_task(
            job_id=job_id,
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=tenant_id,
        )
        return job_state

    def _get_file_state(self, job: Any, file_index: int) -> Optional[Any]:
        normalized_index = int(file_index) - 1
        if normalized_index < 0 or normalized_index >= len(job.files):
            return None
        return job.files[normalized_index]

    def _find_file_state(self, job: Any, *, file_hash: str, file_name: str) -> Tuple[Optional[Any], int]:
        normalized_hash = str(file_hash or "").strip()
        normalized_name = str(file_name or "").strip().lower()
        fallback_match: Tuple[Optional[Any], int] = (None, 0)
        for index, item in enumerate(job.files, start=1):
            item_hash = str(getattr(item, "file_hash", "") or "").strip()
            item_name = str(getattr(item, "file_name", "") or "").strip().lower()
            if normalized_hash and item_hash == normalized_hash:
                if not normalized_name or item_name == normalized_name:
                    return item, index
                if fallback_match[0] is None:
                    fallback_match = (item, index)
            elif not normalized_hash and normalized_name and item_name == normalized_name:
                return item, index
        return fallback_match

    async def begin_job(self, job_id: str) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return False
            job.status = "running"
            job.updated_at = time.time()
        return True

    async def should_skip_file(self, *, job_id: str, file_index: int) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return True
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return True
            file_state = self._get_file_state(job, file_index)
            if file_state is None:
                return False
            return str(file_state.status or "").strip().lower() in SKIPPABLE_FILE_STATUSES

    async def update_file_progress(
        self,
        *,
        job_id: str,
        file_index: int,
        file_name: str,
        stage: str,
        ratio: float,
        message: str,
    ) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return False
            file_state = self._get_file_state(job, file_index)
            if file_state is None:
                return False
            current_status = str(file_state.status or "").strip().lower()
            if current_status in {"cancel_requested", "cancelled"}:
                return False
            next_status = "running"
            if stage == "queued":
                next_status = "queued"
            elif stage == "failed":
                next_status = "failed"
            if current_status in TERMINAL_FILE_STATUSES and next_status not in TERMINAL_FILE_STATUSES:
                return False
            job.updated_at = time.time()
            job.current_file_index = int(file_index)
            job.current_file_name = str(file_name or "")
            job.current_stage = str(stage or "queued") or "queued"
            file_state.status = next_status
            file_state.stage = str(stage or "queued") or "queued"
            file_state.progress_ratio = max(0.0, min(1.0, float(ratio)))
            file_state.message = str(message or file_state.message)
        return True

    async def cancel_file(self, *, job_id: str, file_hash: str, file_name: str = "") -> Optional[Dict[str, Any]]:
        normalized_job_id = str(job_id or "").strip()
        normalized_hash = str(file_hash or "").strip()
        normalized_name = str(file_name or "").strip()
        if not normalized_job_id or (not normalized_hash and not normalized_name):
            return None
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return None
            file_state, file_index = self._find_file_state(
                job,
                file_hash=normalized_hash,
                file_name=normalized_name,
            )
            if file_state is None or file_index <= 0:
                return None
            current_status = str(file_state.status or "").strip().lower() or "queued"
            current_stage = str(file_state.stage or "").strip() or "queued"
            if current_status in TERMINAL_FILE_STATUSES:
                return {
                    "ok": True,
                    "job_id": normalized_job_id,
                    "file_hash": str(file_state.file_hash or ""),
                    "file_name": str(file_state.file_name or ""),
                    "status": current_status,
                    "stage": current_stage,
                    "already_terminal": True,
                }
            file_state.error = ""
            file_state.progress_ratio = 1.0 if current_status == "queued" else max(
                0.0,
                min(1.0, float(file_state.progress_ratio or 0.0)),
            )
            if current_status == "queued":
                file_state.status = "cancelled"
                file_state.stage = "cancelled"
                file_state.message = "Cancelled"
            else:
                file_state.status = "cancel_requested"
                file_state.stage = current_stage
                file_state.message = "Cancel requested"
            job.current_file_index = int(file_index)
            job.current_file_name = str(file_state.file_name or normalized_name)
            job.current_stage = str(file_state.stage or current_stage or "cancelled")
            job.updated_at = time.time()
            return {
                "ok": True,
                "job_id": normalized_job_id,
                "file_hash": str(file_state.file_hash or ""),
                "file_name": str(file_state.file_name or normalized_name),
                "status": str(file_state.status or ""),
                "stage": str(file_state.stage or ""),
                "already_terminal": False,
            }

    async def complete_file(self, *, job_id: str, file_index: int, file_name: str, doc: Any) -> Optional[bool]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return None
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return None
            file_state = self._get_file_state(job, file_index)
            if file_state is not None:
                current_status = str(file_state.status or "").strip().lower()
                if current_status in {"cancel_requested", "cancelled"}:
                    file_state.progress_ratio = 1.0
                    file_state.status = "cancelled"
                    file_state.stage = "cancelled"
                    file_state.message = "Cancelled"
                    file_state.track = ""
                    file_state.cached = False
                    file_state.error = ""
                    job.current_file_index = int(file_index)
                    job.current_file_name = str(file_name or "")
                    job.current_stage = "cancelled"
                    job.updated_at = time.time()
                    return False
                file_state.progress_ratio = 1.0
                file_state.status = "failed" if doc.errors else "completed"
                file_state.stage = "failed" if doc.errors else "completed"
                file_state.message = "提取完成，但存在错误" if doc.errors else "提取完成"
                file_state.track = getattr(doc, "track", "") or ""
                file_state.cached = bool(getattr(doc, "cached", False))
                file_state.error = " | ".join(_sanitize_error_list(getattr(doc, "errors", []) or []))
            job.documents.append(doc)
            if getattr(doc, "errors", None):
                job.failed_files += 1
                doc_errors = _sanitize_error_list(getattr(doc, "errors", []) or [])
                job.errors.append(f"{file_name}: {' | '.join(doc_errors)}")
            else:
                job.completed_files += 1
            job.current_file_index = int(file_index)
            job.current_file_name = str(file_name or "")
            job.current_stage = "completed"
            job.updated_at = time.time()
        return True

    async def fail_file(
        self,
        *,
        job_id: str,
        file_index: int,
        file_name: str,
        error_message: str,
        display_message: str = "提取失败",
    ) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return False
            file_state = self._get_file_state(job, file_index)
            if file_state is not None:
                current_status = str(file_state.status or "").strip().lower()
                if current_status in {"cancel_requested", "cancelled"}:
                    file_state.progress_ratio = 1.0
                    file_state.status = "cancelled"
                    file_state.stage = "cancelled"
                    file_state.error = ""
                    file_state.message = "Cancelled"
                    job.current_file_index = int(file_index)
                    job.current_file_name = str(file_name or "")
                    job.current_stage = "cancelled"
                    job.updated_at = time.time()
                    return True
                file_state.progress_ratio = 1.0
                file_state.status = "failed"
                file_state.stage = "failed"
                file_state.error = _sanitize_error_message(error_message)
                file_state.message = str(display_message or "提取失败")
            job.failed_files += 1
            job.errors.append(f"{file_name}: {_sanitize_error_message(error_message)}")
            job.current_file_index = int(file_index)
            job.current_file_name = str(file_name or "")
            job.current_stage = "failed"
            job.updated_at = time.time()
        return True

    async def append_job_error(self, job_id: str, message: str) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False
        normalized_message = _sanitize_error_message(message)
        if not normalized_message:
            return False
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return False
            job.errors.append(normalized_message)
            job.updated_at = time.time()
        return True

    async def finalize_job(self, job_id: str) -> List[Any]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return []
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return []
            terminal_files = [
                item
                for item in job.files
                if str(getattr(item, "status", "") or "").strip().lower() in TERMINAL_FILE_STATUSES
            ]
            done = len(terminal_files)
            if done < int(job.total_files):
                job.status = "running"
            elif job.completed_files > 0:
                job.status = "completed"
            elif any(str(getattr(item, "status", "") or "").strip().lower() == "failed" for item in terminal_files):
                job.status = "failed"
            else:
                job.status = "failed"
            job.current_stage = (
                "completed" if job.status == "completed" else ("failed" if job.status == "failed" else job.current_stage)
            )
            job.updated_at = time.time()
            return list(job.documents)

    def deserialize_file_state(self, payload: Any) -> Optional[Any]:
        if not isinstance(payload, dict):
            return None
        file_name = str(payload.get("file_name") or "").strip()
        file_hash = str(payload.get("file_hash") or "").strip()
        if not file_name or not file_hash:
            return None
        return self._job_file_state_factory(
            file_name=file_name,
            file_hash=file_hash,
            status=str(payload.get("status") or "queued").strip() or "queued",
            stage=str(payload.get("stage") or "queued").strip() or "queued",
            progress_ratio=max(0.0, min(1.0, float(payload.get("progress_ratio") or 0.0))),
            message=str(payload.get("message") or "").strip(),
            artifact_path=str(payload.get("artifact_path") or "").strip() or None,
            artifact_url=str(payload.get("artifact_url") or "").strip() or None,
            error=str(payload.get("error") or "").strip(),
            track=str(payload.get("track") or "").strip(),
            cached=bool(payload.get("cached")),
        )

    def deserialize_job_state(self, payload: Any) -> Optional[Any]:
        if not isinstance(payload, dict):
            return None
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            return None
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        file_states = [
            file_state
            for item in (payload.get("files") or [])
            if (file_state := self.deserialize_file_state(item)) is not None
        ]
        documents: List[Any] = []
        for item in payload.get("documents") or []:
            try:
                documents.append(self._document_validate(item))
            except Exception:
                continue
        return self._job_state_factory(
            job_id=job_id,
            status=str(payload.get("status") or "queued").strip() or "queued",
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            total_files=max(int(progress.get("total_files") or len(file_states) or 0), len(file_states)),
            completed_files=max(0, int(progress.get("completed_files") or 0)),
            failed_files=max(0, int(progress.get("failed_files") or 0)),
            current_file_index=max(0, int(progress.get("current_file_index") or 0)),
            current_file_name=str(progress.get("current_file_name") or "").strip(),
            current_stage=str(progress.get("current_stage") or "queued").strip() or "queued",
            files=file_states,
            documents=documents,
            errors=_sanitize_error_list(payload.get("errors") or []),
        )

    def build_snapshot_payload(self, job: Any) -> Dict[str, Any]:
        return {
            "version": 1,
            "saved_at": time.time(),
            "job": self.serialize_job(job, include_documents=True),
            "runtime": self.serialize_runtime_spec(job.job_id),
        }

    def load_snapshot_file(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self.state_path(job_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._logger.warning(
                "module2 failed to read extraction job snapshot job=%s: %s: %s",
                job_id,
                type(exc).__name__,
                exc,
            )
            return None
        return payload if isinstance(payload, dict) else None

    def load_loaded_files(self, runtime_spec: Dict[str, Any]) -> List[Tuple[str, bytes, str, str, str, str]]:
        loaded_files: List[Tuple[str, bytes, str, str, str, str]] = []
        for item in runtime_spec.get("loaded_files", []):
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("file_name") or "").strip()
            file_hash = str(item.get("file_hash") or "").strip()
            artifact_path = str(item.get("artifact_path") or "").strip()
            artifact_url = str(item.get("artifact_url") or "").strip()
            mime_type = str(item.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
            if not file_name or not file_hash or not artifact_path:
                continue
            file_bytes = self._safe_artifact_path(artifact_path).read_bytes()
            loaded_files.append((file_name, file_bytes, file_hash, artifact_path, artifact_url, mime_type))
        return loaded_files

    def drop_runtime(self, job_id: str, *, remove_snapshot: bool) -> None:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return
        self.runtime_specs.pop(normalized_job_id, None)
        self.persist_markers.pop(normalized_job_id, None)
        task = self.tasks.get(normalized_job_id)
        if task and task.done():
            self.tasks.pop(normalized_job_id, None)
        if remove_snapshot:
            try:
                self.state_path(normalized_job_id).unlink(missing_ok=True)
            except Exception:
                pass

    def persist_interval_sec(self) -> float:
        return max(0.0, float(os.getenv("MODULE2_EXTRACT_JOB_PERSIST_INTERVAL_SEC", "1.0")))

    async def persist_snapshot(self, job_id: str, force: bool = False) -> None:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return
        now_ts = time.time()
        if not force:
            last_ts = float(self.persist_markers.get(normalized_job_id) or 0.0)
            if (now_ts - last_ts) < self.persist_interval_sec():
                return
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                snapshot_payload = None
            else:
                snapshot_payload = self.build_snapshot_payload(job)
        if snapshot_payload is None:
            self.drop_runtime(normalized_job_id, remove_snapshot=True)
            return
        try:
            self._write_json_file_atomic(self.state_path(normalized_job_id), snapshot_payload)
            self.persist_markers[normalized_job_id] = now_ts
        except Exception as exc:
            self._logger.warning(
                "module2 failed to persist extraction job snapshot job=%s: %s: %s",
                normalized_job_id,
                type(exc).__name__,
                exc,
            )

    def schedule_task(
        self,
        *,
        job_id: str,
        loaded_files: List[Tuple[str, bytes, str, str, str, str]],
        schema_obj: Dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False
        existing_task = self.tasks.get(normalized_job_id)
        if existing_task and not existing_task.done():
            return False

        task = self._task_factory(
            self._run_extraction_job(
                job_id=normalized_job_id,
                loaded_files=loaded_files,
                schema_obj=schema_obj,
                schema_digest=schema_digest,
                max_retries=max_retries,
                tenant_id=tenant_id,
            )
        )
        self.tasks[normalized_job_id] = task

        def _cleanup_task(done_task: asyncio.Task[Any]) -> None:
            current = self.tasks.get(normalized_job_id)
            if current is done_task:
                self.tasks.pop(normalized_job_id, None)

        task.add_done_callback(_cleanup_task)
        return True

    async def mark_resume_failed(self, job_id: str, message: str) -> None:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return
        async with self.lock:
            job = self.jobs.get(normalized_job_id)
            if not job:
                return
            job.status = "failed"
            job.updated_at = time.time()
            job.current_stage = "failed"
            normalized_message = _sanitize_error_message(message)
            if normalized_message and normalized_message not in job.errors:
                job.errors.append(normalized_message)
            for item in job.files:
                if item.status not in TERMINAL_FILE_STATUSES:
                    item.status = "failed"
                    item.stage = "failed"
                    item.progress_ratio = 1.0
                    item.error = normalized_message
                    item.message = "任务恢复失败"
            job.failed_files = sum(1 for item in job.files if item.status == "failed")
        await self.persist_snapshot(normalized_job_id, force=True)

    async def restore_from_snapshot(self, job_id: str) -> Optional[Any]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return None
        snapshot = self.load_snapshot_file(normalized_job_id)
        if not snapshot:
            return None
        job = self.deserialize_job_state(snapshot.get("job"))
        if not job:
            return None
        runtime_spec = self.normalize_runtime_spec(snapshot.get("runtime"))
        async with self.lock:
            self.jobs[normalized_job_id] = job
            self.runtime_specs[normalized_job_id] = runtime_spec
        if not job.terminal():
            try:
                loaded_files = self.load_loaded_files(runtime_spec)
            except Exception as exc:
                await self.mark_resume_failed(
                    normalized_job_id,
                    f"resume_payload_unavailable: {type(exc).__name__}: {exc}",
                )
            else:
                if not loaded_files:
                    await self.mark_resume_failed(
                        normalized_job_id,
                        "resume_payload_unavailable: no resumable uploaded files found",
                    )
                    async with self.lock:
                        return self.jobs.get(normalized_job_id)
                self.schedule_task(
                    job_id=normalized_job_id,
                    loaded_files=loaded_files,
                    schema_obj=runtime_spec.get("schema") if isinstance(runtime_spec.get("schema"), dict) else {},
                    schema_digest=str(runtime_spec.get("schema_digest") or "").strip(),
                    max_retries=max(0, int(runtime_spec.get("max_retries") or 0)),
                    tenant_id=str(runtime_spec.get("tenant_id") or "").strip(),
                )
        return job

    async def find_job(self, job_id: str) -> Optional[Any]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return None
        async with self.lock:
            self.cleanup_jobs_locked()
            job = self.jobs.get(normalized_job_id)
        if job is not None:
            return job
        return await self.restore_from_snapshot(normalized_job_id)

    def extraction_job_ttl_sec(self) -> float:
        return max(300.0, float(os.getenv("MODULE2_EXTRACT_JOB_TTL_SEC", "7200")))

    def extraction_job_cap(self) -> int:
        return max(16, int(os.getenv("MODULE2_EXTRACT_JOB_CAP", "240")))

    def cleanup_jobs_locked(self) -> None:
        ttl_sec = self.extraction_job_ttl_sec()
        cap = self.extraction_job_cap()
        now_ts = time.time()
        removed_job_ids = [
            job_id
            for job_id, job in self.jobs.items()
            if job.terminal() and (now_ts - float(job.updated_at)) > ttl_sec
        ]
        for job_id in removed_job_ids:
            self.jobs.pop(job_id, None)
        if len(self.jobs) > cap:
            ordered_terminal = sorted(
                [item for item in self.jobs.values() if item.terminal()],
                key=lambda item: float(item.updated_at),
            )
            removable = max(0, len(self.jobs) - cap)
            for item in ordered_terminal[:removable]:
                removed_job_ids.append(item.job_id)
                self.jobs.pop(item.job_id, None)
        for job_id in removed_job_ids:
            self.drop_runtime(job_id, remove_snapshot=True)

    async def recover_from_snapshots(self) -> None:
        recovered = 0
        resumed = 0
        for snapshot_path in sorted(self._state_root_factory().glob("*.json")):
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._logger.warning(
                    "module2 failed to parse extraction job snapshot path=%s: %s: %s",
                    snapshot_path,
                    type(exc).__name__,
                    exc,
                )
                continue
            if not isinstance(payload, dict):
                continue
            job = self.deserialize_job_state(payload.get("job"))
            if not job:
                continue
            runtime_spec = self.normalize_runtime_spec(payload.get("runtime"))
            async with self.lock:
                self.cleanup_jobs_locked()
                self.jobs[job.job_id] = job
                self.runtime_specs[job.job_id] = runtime_spec
            recovered += 1
            if job.terminal():
                continue
            try:
                loaded_files = self.load_loaded_files(runtime_spec)
            except Exception as exc:
                await self.mark_resume_failed(
                    job.job_id,
                    f"resume_payload_unavailable: {type(exc).__name__}: {exc}",
                )
                continue
            if not loaded_files:
                await self.mark_resume_failed(
                    job.job_id,
                    "resume_payload_unavailable: no resumable uploaded files found",
                )
                continue
            if self.schedule_task(
                job_id=job.job_id,
                loaded_files=loaded_files,
                schema_obj=runtime_spec.get("schema") if isinstance(runtime_spec.get("schema"), dict) else {},
                schema_digest=str(runtime_spec.get("schema_digest") or "").strip(),
                max_retries=max(0, int(runtime_spec.get("max_retries") or 0)),
                tenant_id=str(runtime_spec.get("tenant_id") or "").strip(),
            ):
                resumed += 1
        if recovered > 0:
            self._logger.info("module2 recovered extraction jobs=%s resumed=%s", recovered, resumed)

    async def shutdown_runtime(self, *, persist_snapshot: PersistSnapshotFn) -> None:
        for job_id in list(self.jobs.keys()):
            await persist_snapshot(str(job_id), True)
        running_tasks = [task for task in self.tasks.values() if not task.done()]
        if running_tasks:
            for task in running_tasks:
                task.cancel()
            await asyncio.gather(*running_tasks, return_exceptions=True)
        self.tasks.clear()
