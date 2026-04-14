from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
from urllib.parse import unquote

from fastapi import HTTPException


ConvertWordToPdfFn = Callable[..., Awaitable[Tuple[bytes, Dict[str, Any]]]]
SafeArtifactPathFn = Callable[[str], Path]
ArtifactFragmentFromPathFn = Callable[[Any], str]
ArtifactUrlFromFragmentFn = Callable[[str], str]
TimeoutSecFactory = Callable[[], float]
TaskFactory = Callable[[Awaitable[Any]], asyncio.Task[Any]]
IsWordFileFn = Callable[[str], bool]
OfficeConvertEnabledFn = Callable[[], bool]
EnsureJobStartedFn = Callable[..., Awaitable[Any]]
SerializeJobFn = Callable[[Any], Dict[str, Any]]
GetStatusPayloadFn = Callable[[str], Awaitable[Dict[str, Any]]]


@dataclass
class OfficePreviewJob:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    file_name: str
    file_hash: str
    artifact_path: Optional[str]
    artifact_url: Optional[str]
    error: str = ""
    converter: str = ""
    elapsed_ms: int = 0


class OfficePreviewService:
    """Application service for DOC/DOCX preview conversion runtime."""

    def __init__(
        self,
        *,
        convert_word_to_pdf: ConvertWordToPdfFn,
        safe_artifact_path: SafeArtifactPathFn,
        artifact_fragment_from_path: ArtifactFragmentFromPathFn,
        artifact_url_from_fragment: ArtifactUrlFromFragmentFn,
        timeout_sec_factory: TimeoutSecFactory,
        task_factory: TaskFactory | None = None,
    ) -> None:
        self._convert_word_to_pdf = convert_word_to_pdf
        self._safe_artifact_path = safe_artifact_path
        self._artifact_fragment_from_path = artifact_fragment_from_path
        self._artifact_url_from_fragment = artifact_url_from_fragment
        self._timeout_sec_factory = timeout_sec_factory
        self._task_factory = task_factory or asyncio.create_task
        self.jobs: Dict[str, OfficePreviewJob] = {}
        self.lock = asyncio.Lock()

    def job_count(self) -> int:
        return len(self.jobs)

    async def clear(self) -> None:
        async with self.lock:
            self.jobs.clear()

    def cleanup_jobs_locked(self) -> None:
        ttl_sec = max(120.0, float(os.getenv("MODULE2_OFFICE_PREVIEW_JOB_TTL_SEC", "1800")))
        cap = max(20, int(os.getenv("MODULE2_OFFICE_PREVIEW_JOB_CAP", "240")))
        now = time.time()
        expired = [
            job_id
            for job_id, job in self.jobs.items()
            if (now - float(job.updated_at or job.created_at)) > ttl_sec
        ]
        for job_id in expired:
            self.jobs.pop(job_id, None)
        if len(self.jobs) <= cap:
            return
        ordered = sorted(self.jobs.values(), key=lambda item: item.updated_at)
        for item in ordered[: max(0, len(self.jobs) - cap)]:
            self.jobs.pop(item.job_id, None)

    def serialize_job(self, job: OfficePreviewJob) -> Dict[str, Any]:
        return {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "file_name": job.file_name,
            "file_hash": job.file_hash,
            "artifact_path": job.artifact_path,
            "artifact_url": job.artifact_url,
            "error": job.error,
            "converter": job.converter,
            "elapsed_ms": int(job.elapsed_ms or 0),
            "terminal": job.status in {"completed", "failed"},
        }

    async def get_status_payload(self, job_id: str) -> Dict[str, Any]:
        async with self.lock:
            self.cleanup_jobs_locked()
            job = self.jobs.get(str(job_id or "").strip())
            if job is None:
                raise FileNotFoundError("preview_job_not_found")
            return self.serialize_job(job)

    async def ensure_job_started(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
    ) -> OfficePreviewJob:
        normalized_hash = str(file_hash or "").strip().lower()
        if not normalized_hash:
            raise ValueError("file_hash is required for office preview job")

        created_job: OfficePreviewJob | None = None
        async with self.lock:
            self.cleanup_jobs_locked()
            existing = self._find_by_hash_locked(normalized_hash, file_name)
            if existing is not None:
                if existing.status == "completed" and not self._artifact_exists(existing):
                    existing.status = "failed"
                    existing.updated_at = time.time()
                    existing.artifact_path = None
                    existing.artifact_url = None
                    existing.error = "stale_preview_artifact_missing"
                else:
                    return existing

            now = time.time()
            created_job = OfficePreviewJob(
                job_id=f"preview_{uuid.uuid4().hex[:16]}",
                status="queued",
                created_at=now,
                updated_at=now,
                file_name=file_name,
                file_hash=normalized_hash,
                artifact_path=None,
                artifact_url=None,
                error="",
            )
            self.jobs[created_job.job_id] = created_job

        if created_job is not None:
            self._task_factory(self.run_job(created_job.job_id, file_name, file_bytes))
            return created_job
        raise RuntimeError("office_preview_job_create_failed")

    async def await_or_reuse_pdf(
        self,
        *,
        file_name: str,
        file_hash: str,
        timeout_sec: float,
    ) -> Tuple[Optional[bytes], Dict[str, Any]]:
        deadline = time.perf_counter() + max(2.0, float(timeout_sec))
        wait_started = time.perf_counter()
        saw_running = False

        while True:
            async with self.lock:
                self.cleanup_jobs_locked()
                job = self._find_by_hash_locked(file_hash, file_name)
                if job is None:
                    return None, {}

                if job.status == "completed":
                    try:
                        pdf_bytes = self._read_artifact_bytes(job)
                    except Exception as exc:
                        job.status = "failed"
                        job.updated_at = time.time()
                        if not str(job.error or "").strip():
                            job.error = f"artifact_read_failed:{type(exc).__name__}:{exc}"
                        return None, {
                            "office_pdf_preview_error": job.error,
                            "office_pdf_preview_job_id": job.job_id,
                        }
                    return pdf_bytes, {
                        "office_pdf_preview_reused": True,
                        "office_pdf_preview_job_id": job.job_id,
                        "artifact_path": job.artifact_path,
                        "artifact_url": job.artifact_url,
                        "converter": str(job.converter or "").strip() or "preview_cache",
                        "elapsed_ms": int(job.elapsed_ms or 0),
                        "waited_ms": int((time.perf_counter() - wait_started) * 1000),
                    }

                if job.status == "failed":
                    return None, {
                        "office_pdf_preview_error": str(job.error or "").strip() or "office_preview_failed",
                        "office_pdf_preview_job_id": job.job_id,
                    }

                saw_running = job.status in {"queued", "running"}

            if time.perf_counter() >= deadline:
                if saw_running:
                    raise TimeoutError(f"office_preview_wait_timeout:{file_name}")
                return None, {}
            await asyncio.sleep(0.35)

    async def run_job(self, job_id: str, file_name: str, file_bytes: bytes) -> None:
        async with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.status = "running"
            job.updated_at = time.time()

        try:
            timeout_sec = max(20.0, float(self._timeout_sec_factory()))
            pdf_bytes, convert_meta = await self._convert_word_to_pdf(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=timeout_sec,
            )
            async with self.lock:
                job = self.jobs.get(job_id)
                if not job:
                    return
                file_hash = str(job.file_hash or "").strip().lower()
            fragment = str(convert_meta.get("artifact_path") or "").strip()
            artifact_url = str(convert_meta.get("artifact_url") or "").strip()
            if not fragment or not artifact_url:
                fragment, artifact_url = self._write_artifact(
                    file_name=file_name,
                    file_hash=file_hash,
                    pdf_bytes=pdf_bytes,
                    convert_meta=convert_meta,
                )
            async with self.lock:
                job = self.jobs.get(job_id)
                if not job:
                    return
                job.status = "completed"
                job.updated_at = time.time()
                job.artifact_path = fragment
                job.artifact_url = artifact_url
                job.error = ""
                job.converter = str(convert_meta.get("converter", "") or "")
                job.elapsed_ms = int(convert_meta.get("elapsed_ms", 0) or 0)
        except Exception as exc:
            async with self.lock:
                job = self.jobs.get(job_id)
                if not job:
                    return
                job.status = "failed"
                job.updated_at = time.time()
                job.error = f"{type(exc).__name__}: {exc}"
                job.converter = ""
                job.elapsed_ms = 0

    def _normalize_content_hash(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        compact = re.sub(r"[^a-f0-9]+", "", raw)
        if len(compact) >= 24:
            return compact
        if raw:
            return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
        return hashlib.sha256(b"module2_office_preview").hexdigest()

    def _storage_fragments(self, file_hash: str) -> Tuple[str, str]:
        normalized_hash = self._normalize_content_hash(file_hash)
        rel_dir = Path("preview") / "op" / normalized_hash[:2]
        pdf_fragment = str((rel_dir / f"{normalized_hash}.pdf").as_posix())
        meta_fragment = str((rel_dir / f"{normalized_hash}.json").as_posix())
        return pdf_fragment, meta_fragment

    def _legacy_storage_fragments(self, file_hash: str) -> Tuple[str, str]:
        normalized_hash = self._normalize_content_hash(file_hash)
        rel_dir = Path("preview") / "office_pdf" / "by_source" / normalized_hash[:2] / normalized_hash
        pdf_fragment = str((rel_dir / "source.pdf").as_posix())
        meta_fragment = str((rel_dir / "meta.json").as_posix())
        return pdf_fragment, meta_fragment

    def _write_artifact(
        self,
        *,
        file_name: str,
        file_hash: str,
        pdf_bytes: bytes,
        convert_meta: Dict[str, Any],
    ) -> Tuple[str, str]:
        pdf_fragment, meta_fragment = self._storage_fragments(file_hash)
        pdf_path = self._safe_artifact_path(pdf_fragment)
        meta_path = self._safe_artifact_path(meta_fragment)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        payload = {
            "version": "module2-office-preview-v1",
            "file_name": str(file_name or ""),
            "file_hash": self._normalize_content_hash(file_hash),
            "artifact_path": pdf_fragment,
            "artifact_url": self._artifact_url_from_fragment(pdf_fragment),
            "converter": str(convert_meta.get("converter", "") or ""),
            "elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "pdf_size": len(pdf_bytes),
            "updated_at": time.time(),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pdf_fragment, self._artifact_url_from_fragment(pdf_fragment)

    def _load_record(self, file_hash: str) -> Dict[str, Any]:
        normalized_hash = self._normalize_content_hash(file_hash)
        for pdf_fragment, meta_fragment in (
            self._storage_fragments(normalized_hash),
            self._legacy_storage_fragments(normalized_hash),
        ):
            pdf_path = self._safe_artifact_path(pdf_fragment)
            if not pdf_path.exists() or not pdf_path.is_file():
                continue
            meta_path = self._safe_artifact_path(meta_fragment)
            payload: Dict[str, Any] = {}
            if meta_path.exists() and meta_path.is_file():
                try:
                    raw = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                    if isinstance(raw, dict):
                        payload = dict(raw)
                except Exception:
                    payload = {}
            payload["file_hash"] = normalized_hash
            payload["artifact_path"] = pdf_fragment
            payload["artifact_url"] = self._artifact_url_from_fragment(pdf_fragment)
            payload["updated_at"] = float(payload.get("updated_at", pdf_path.stat().st_mtime) or pdf_path.stat().st_mtime)
            payload["file_name"] = str(payload.get("file_name", "") or "")
            payload["converter"] = str(payload.get("converter", "") or "")
            payload["elapsed_ms"] = int(payload.get("elapsed_ms", 0) or 0)
            return payload
        return {}

    def _recover_job_from_disk_locked(self, *, file_hash: str, file_name: str = "") -> Optional[OfficePreviewJob]:
        record = self._load_record(file_hash)
        if not record:
            return None
        normalized_hash = str(record.get("file_hash") or self._normalize_content_hash(file_hash)).strip().lower()
        updated_at = float(record.get("updated_at", time.time()) or time.time())
        recovered = OfficePreviewJob(
            job_id=f"preview_disk_{normalized_hash[:16]}",
            status="completed",
            created_at=updated_at,
            updated_at=updated_at,
            file_name=str(record.get("file_name") or file_name or ""),
            file_hash=normalized_hash,
            artifact_path=str(record.get("artifact_path") or ""),
            artifact_url=str(record.get("artifact_url") or ""),
            error="",
            converter=str(record.get("converter") or "preview_disk_cache"),
            elapsed_ms=int(record.get("elapsed_ms", 0) or 0),
        )
        self.jobs[recovered.job_id] = recovered
        return recovered

    def _artifact_exists(self, job: OfficePreviewJob) -> bool:
        fragment = self._artifact_fragment_from_path(job.artifact_path)
        if not fragment:
            raw_url = str(job.artifact_url or "").strip()
            prefix = "/extract/artifact/"
            if raw_url.startswith(prefix):
                fragment = unquote(raw_url[len(prefix) :]).strip().strip("/")
        if not fragment:
            return False
        try:
            target = self._safe_artifact_path(fragment)
        except Exception:
            return False
        return target.exists() and target.is_file()

    def _find_by_hash_locked(self, file_hash: str, file_name: str = "") -> Optional[OfficePreviewJob]:
        normalized = str(file_hash or "").strip().lower()
        if not normalized:
            return None

        matches = [
            job
            for job in self.jobs.values()
            if str(job.file_hash or "").strip().lower() == normalized
        ]
        completed_matches = [job for job in matches if job.status == "completed" and self._artifact_exists(job)]
        if completed_matches:
            completed_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
            return completed_matches[0]

        running_matches = [job for job in matches if job.status in {"queued", "running"}]
        if running_matches:
            running_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
            return running_matches[0]

        recovered = self._recover_job_from_disk_locked(file_hash=normalized, file_name=file_name)
        if recovered is not None:
            return recovered

        if not matches:
            return None
        matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
        return matches[0]

    def _read_artifact_bytes(self, job: OfficePreviewJob) -> bytes:
        fragment = self._artifact_fragment_from_path(job.artifact_path)
        if not fragment:
            raise FileNotFoundError("office_preview_artifact_missing_fragment")
        target = self._safe_artifact_path(fragment)
        return target.read_bytes()


class OfficePreviewRequestService:
    """Application service for office preview request endpoints."""

    def __init__(
        self,
        *,
        is_word_file: IsWordFileFn,
        office_convert_enabled: OfficeConvertEnabledFn,
        ensure_job_started: EnsureJobStartedFn,
        serialize_job: SerializeJobFn,
        get_status_payload: GetStatusPayloadFn,
    ) -> None:
        self._is_word_file = is_word_file
        self._office_convert_enabled = office_convert_enabled
        self._ensure_job_started = ensure_job_started
        self._serialize_job = serialize_job
        self._get_status_payload = get_status_payload

    async def start(self, file: Any) -> Dict[str, Any]:
        file_name = getattr(file, "filename", None) or "unknown.docx"
        if not self._is_word_file(file_name):
            raise HTTPException(status_code=400, detail="Only .doc/.docx preview conversion is supported")
        if not self._office_convert_enabled():
            raise HTTPException(status_code=503, detail="DOC/DOCX preview conversion is disabled")

        max_file_mb = max(1, int(os.getenv("MODULE2_MAX_FILE_MB", "25")))
        max_file_bytes = max_file_mb * 1024 * 1024
        file_bytes = await file.read(max_file_bytes + 1)
        if len(file_bytes) > max_file_bytes:
            raise HTTPException(status_code=413, detail=f"File too large. Max {max_file_mb}MB")
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        created = await self._ensure_job_started(
            file_name=file_name,
            file_bytes=file_bytes,
            file_hash=file_hash,
        )
        return self._serialize_job(created)

    async def get_status(self, job_id: str) -> Dict[str, Any]:
        try:
            return await self._get_status_payload(job_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Preview job not found") from exc


# Backward-compatible aliases during migration.
OfficePreviewRuntime = OfficePreviewService
OfficePreviewRequestRuntime = OfficePreviewRequestService

