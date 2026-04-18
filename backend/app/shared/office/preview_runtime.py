from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app.core.paths import resolve_runtime_root_dir

from .conversion import convert_word_bytes_to_pdf, is_word_file


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _resolve_data_root() -> Path:
    runtime_root = resolve_runtime_root_dir().resolve()
    explicit = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if explicit:
        resolved = Path(explicit).expanduser().resolve()
        if resolved == runtime_root:
            return (runtime_root / "runtime-data").resolve()
        return resolved
    return (runtime_root / "runtime-data").resolve()


def _resolve_preview_root() -> Path:
    explicit = str(os.getenv("OFFICE_RUNTIME_PREVIEW_ROOT_DIR", "") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (_resolve_data_root() / "office-runtime" / "preview").resolve()


@dataclass
class OfficePreviewJob:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    file_name: str
    file_hash: str
    artifact_path: str = ""
    error: str = ""
    converter: str = ""
    elapsed_ms: int = 0


class OfficePreviewRuntime:
    def __init__(
        self,
        *,
        preview_root: Path | None = None,
        preview_timeout_sec: float | None = None,
        job_ttl_sec: float | None = None,
        job_cap: int | None = None,
        word_file_detector: Callable[[str], bool] | None = None,
        word_pdf_converter: Callable[..., tuple[bytes, dict[str, Any]]] | None = None,
    ) -> None:
        self.preview_root = (preview_root or _resolve_preview_root()).resolve()
        self.preview_root.mkdir(parents=True, exist_ok=True)
        self.preview_timeout_sec = max(
            20.0,
            float(preview_timeout_sec or _env_float("OFFICE_RUNTIME_PREVIEW_TIMEOUT_SEC", 120.0)),
        )
        self.job_ttl_sec = max(
            120.0,
            float(job_ttl_sec or _env_float("OFFICE_RUNTIME_PREVIEW_JOB_TTL_SEC", 1800.0)),
        )
        self.job_cap = max(20, int(job_cap or _env_int("OFFICE_RUNTIME_PREVIEW_JOB_CAP", 240)))
        self._word_file_detector = word_file_detector or is_word_file
        self._word_pdf_converter = word_pdf_converter or convert_word_bytes_to_pdf
        self._jobs: dict[str, OfficePreviewJob] = {}
        self._lock = threading.RLock()

    def start(self, *, file_name: str, file_bytes: bytes) -> dict[str, Any]:
        normalized_name = str(file_name or "").strip()
        if not normalized_name:
            raise ValueError("empty file name")
        if not self._word_file_detector(normalized_name):
            raise ValueError("Only .doc/.docx preview conversion is supported")
        if not file_bytes:
            raise ValueError("empty office payload")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        with self._lock:
            self._cleanup_locked()
            existing = self._find_existing_locked(file_hash)
            if existing is not None:
                return self.serialize(existing)

            recovered = self._recover_from_disk_locked(file_name=normalized_name, file_hash=file_hash)
            if recovered is not None:
                return self.serialize(recovered)

            now = time.time()
            job = OfficePreviewJob(
                job_id=f"preview_{hashlib.sha1(f'{file_hash}:{now}'.encode('utf-8', 'ignore')).hexdigest()[:16]}",
                status="queued",
                created_at=now,
                updated_at=now,
                file_name=normalized_name,
                file_hash=file_hash,
            )
            self._jobs[job.job_id] = job

        worker = threading.Thread(
            target=self._run_job,
            args=(job.job_id, normalized_name, file_bytes),
            name=f"shared-office-preview-{job.job_id[:8]}",
            daemon=True,
        )
        worker.start()
        return self.serialize(job)

    def get_status(self, job_id: str) -> dict[str, Any]:
        normalized_job_id = str(job_id or "").strip()
        with self._lock:
            self._cleanup_locked()
            job = self._jobs.get(normalized_job_id)
            if job is None:
                raise FileNotFoundError("Preview job not found")
            return self.serialize(job)

    def get_artifact(self, job_id: str) -> tuple[bytes, str, str]:
        normalized_job_id = str(job_id or "").strip()
        with self._lock:
            self._cleanup_locked()
            job = self._jobs.get(normalized_job_id)
            if job is None:
                raise FileNotFoundError("Preview job not found")
            if job.status != "completed":
                raise RuntimeError(f"preview_job_not_ready:{job.status}")
            artifact_path = Path(job.artifact_path).resolve()

        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError("Preview artifact not found")
        content = artifact_path.read_bytes()
        content_type = mimetypes.guess_type(str(artifact_path))[0] or "application/pdf"
        return content, content_type, artifact_path.name

    def _run_job(self, job_id: str, file_name: str, file_bytes: bytes) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.updated_at = time.time()

        try:
            pdf_bytes, convert_meta = self._word_pdf_converter(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=self.preview_timeout_sec,
            )
            artifact_path = self._write_artifact(
                file_name=file_name,
                file_hash=hashlib.sha256(file_bytes).hexdigest(),
                pdf_bytes=pdf_bytes,
                convert_meta=convert_meta,
            )
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "completed"
                job.updated_at = time.time()
                job.artifact_path = str(artifact_path)
                job.error = ""
                job.converter = str(convert_meta.get("converter") or "")
                job.elapsed_ms = int(convert_meta.get("elapsed_ms") or 0)
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "failed"
                job.updated_at = time.time()
                job.error = f"{type(exc).__name__}: {exc}"
                job.converter = ""
                job.elapsed_ms = 0

    def _artifact_paths(self, *, file_hash: str) -> tuple[Path, Path]:
        artifact_dir = (self.preview_root / file_hash[:2] / file_hash).resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir / "artifact.pdf", artifact_dir / "meta.json"

    def _write_artifact(
        self,
        *,
        file_name: str,
        file_hash: str,
        pdf_bytes: bytes,
        convert_meta: dict[str, Any],
    ) -> Path:
        artifact_path, meta_path = self._artifact_paths(file_hash=file_hash)
        artifact_path.write_bytes(pdf_bytes)
        payload = {
            "version": "shared-office-preview-v1",
            "file_name": str(file_name or ""),
            "file_hash": str(file_hash or "").strip().lower(),
            "artifact_path": str(artifact_path),
            "converter": str(convert_meta.get("converter") or ""),
            "elapsed_ms": int(convert_meta.get("elapsed_ms") or 0),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "pdf_size": len(pdf_bytes),
            "updated_at": time.time(),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return artifact_path

    def _load_record_from_disk(self, *, file_hash: str) -> dict[str, Any]:
        artifact_path, meta_path = self._artifact_paths(file_hash=file_hash)
        if not artifact_path.exists() or not artifact_path.is_file():
            return {}
        payload: dict[str, Any] = {}
        if meta_path.exists() and meta_path.is_file():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(raw, dict):
                    payload = dict(raw)
            except Exception:
                payload = {}
        payload["artifact_path"] = str(payload.get("artifact_path") or artifact_path)
        payload["updated_at"] = float(payload.get("updated_at") or artifact_path.stat().st_mtime or time.time())
        payload["file_hash"] = str(payload.get("file_hash") or file_hash).strip().lower()
        payload["file_name"] = str(payload.get("file_name") or "")
        payload["converter"] = str(payload.get("converter") or "")
        payload["elapsed_ms"] = int(payload.get("elapsed_ms") or 0)
        return payload

    def _recover_from_disk_locked(self, *, file_name: str, file_hash: str) -> OfficePreviewJob | None:
        record = self._load_record_from_disk(file_hash=file_hash)
        if not record:
            return None
        recovered = OfficePreviewJob(
            job_id=f"preview_disk_{file_hash[:16]}",
            status="completed",
            created_at=float(record.get("updated_at") or time.time()),
            updated_at=float(record.get("updated_at") or time.time()),
            file_name=str(record.get("file_name") or file_name or ""),
            file_hash=file_hash,
            artifact_path=str(record.get("artifact_path") or ""),
            error="",
            converter=str(record.get("converter") or ""),
            elapsed_ms=int(record.get("elapsed_ms") or 0),
        )
        self._jobs[recovered.job_id] = recovered
        return recovered

    def _find_existing_locked(self, file_hash: str) -> OfficePreviewJob | None:
        matches = [job for job in self._jobs.values() if str(job.file_hash or "").strip().lower() == file_hash]
        completed = [
            job
            for job in matches
            if job.status == "completed"
            and job.artifact_path
            and Path(job.artifact_path).exists()
        ]
        if completed:
            completed.sort(key=lambda item: float(item.updated_at or item.created_at or 0.0), reverse=True)
            return completed[0]
        running = [job for job in matches if job.status in {"queued", "running"}]
        if running:
            running.sort(key=lambda item: float(item.updated_at or item.created_at or 0.0), reverse=True)
            return running[0]
        return None

    def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if (now - float(job.updated_at or job.created_at or 0.0)) > self.job_ttl_sec
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        if len(self._jobs) <= self.job_cap:
            return
        ordered = sorted(
            self._jobs.values(),
            key=lambda item: float(item.updated_at or item.created_at or 0.0),
        )
        for item in ordered[: max(0, len(self._jobs) - self.job_cap)]:
            self._jobs.pop(item.job_id, None)

    @staticmethod
    def serialize(job: OfficePreviewJob) -> dict[str, Any]:
        return {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "file_name": job.file_name,
            "file_hash": job.file_hash,
            "artifact_path": job.artifact_path,
            "artifact_url": "",
            "error": job.error,
            "converter": job.converter,
            "elapsed_ms": int(job.elapsed_ms or 0),
            "terminal": job.status in {"completed", "failed"},
        }


@lru_cache(maxsize=1)
def get_office_preview_runtime() -> OfficePreviewRuntime:
    return OfficePreviewRuntime()
