from __future__ import annotations

import atexit
import concurrent.futures
import copy
import hashlib
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote

from fastapi import HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.modules.module2.core.config import get_extraction_settings


WORD_EXTENSIONS = {".doc", ".docx"}


@dataclass
class _WordComWorkerRequest:
    input_path: Path
    output_path: Path
    future: concurrent.futures.Future[None]


class _WordComWarmWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: queue.Queue[_WordComWorkerRequest | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_requested = False
        self._last_used_at = 0.0
        self._thread_ready = threading.Event()
        self._startup_error = ""

    def submit(self, *, input_path: Path, output_path: Path, timeout_sec: float) -> None:
        self._ensure_thread()
        ready_ok = self._thread_ready.wait(timeout=max(5.0, min(30.0, float(timeout_sec))))
        if not ready_ok:
            raise TimeoutError("word_com_worker_start_timeout")
        if self._startup_error:
            raise RuntimeError(self._startup_error)
        if not self._thread or not self._thread.is_alive():
            raise RuntimeError("word_com_worker_not_running")

        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._queue.put(_WordComWorkerRequest(input_path=input_path, output_path=output_path, future=future))
        future.result(timeout=max(20.0, float(timeout_sec)))

    def close(self) -> None:
        thread: threading.Thread | None = None
        with self._lock:
            self._stop_requested = True
            thread = self._thread
            if thread and thread.is_alive():
                self._queue.put(None)
        if thread and thread.is_alive():
            thread.join(timeout=5.0)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_requested = False
            self._thread_ready.clear()
            self._startup_error = ""
            self._thread = threading.Thread(
                target=self._run_loop,
                name="extraction-word-com-worker",
                daemon=True,
            )
            self._thread.start()

    def _run_loop(self) -> None:
        pythoncom = None
        win32_client = None
        word = None
        idle_sec = max(30.0, float(os.getenv("MODULE2_WORD_COM_WARM_WORKER_IDLE_SEC", "300")))
        try:
            import pythoncom as _pythoncom  # type: ignore
            import win32com.client as _win32_client  # type: ignore

            pythoncom = _pythoncom
            win32_client = _win32_client
            pythoncom.CoInitialize()
            self._thread_ready.set()

            while not self._stop_requested:
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    if word is not None and idle_sec > 0 and (time.time() - self._last_used_at) >= idle_sec:
                        word = self._dispose_word(word)
                    continue

                if item is None:
                    break

                try:
                    word = self._ensure_word(word, win32_client)
                    self._perform(word=word, item=item)
                    self._last_used_at = time.time()
                    item.future.set_result(None)
                except Exception as exc:
                    word = self._dispose_word(word)
                    item.future.set_exception(exc)
                finally:
                    self._queue.task_done()
        except Exception as exc:
            with self._lock:
                self._startup_error = f"word_com_worker_init_failed:{type(exc).__name__}:{exc}"
            self._thread_ready.set()
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None and not item.future.done():
                    item.future.set_exception(RuntimeError(self._startup_error or f"word_com_worker_init_failed:{exc}"))
                self._queue.task_done()
        finally:
            self._dispose_word(word)
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    @staticmethod
    def _ensure_word(word: Any, win32_client: Any) -> Any:
        if word is not None:
            return word
        word = win32_client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        return word

    @staticmethod
    def _dispose_word(word: Any) -> None:
        if word is None:
            return None
        try:
            word.Quit()
        except Exception:
            pass
        return None

    @staticmethod
    def _perform(*, word: Any, item: _WordComWorkerRequest) -> None:
        doc = None
        try:
            doc = word.Documents.Open(
                str(item.input_path),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
            )
            doc.SaveAs(str(item.output_path), FileFormat=17)
        finally:
            try:
                if doc is not None:
                    doc.Close(False)
            except Exception:
                pass


_WORD_COM_WARM_WORKER = _WordComWarmWorker()
atexit.register(_WORD_COM_WARM_WORKER.close)


def is_word_file(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in WORD_EXTENSIONS


def convert_word_bytes_to_pdf(*, file_name: str, file_bytes: bytes, timeout_sec: float = 90.0) -> tuple[bytes, dict[str, Any]]:
    if not file_bytes:
        raise ValueError("empty office payload")

    ext = Path(file_name or "").suffix.lower()
    if ext not in WORD_EXTENSIONS:
        raise ValueError(f"unsupported office extension: {ext or 'unknown'}")

    timeout = max(20.0, float(timeout_sec))
    start = time.perf_counter()
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="extraction_office_pdf_") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / f"input{ext}"
        output_path = tmp_dir / "input.pdf"
        input_path.write_bytes(file_bytes)

        for backend in _word_pdf_backend_order():
            if backend == "libreoffice":
                soffice_path = _resolve_soffice_path()
                if not soffice_path:
                    errors.append("libreoffice:not_available")
                    continue
                try:
                    _convert_with_soffice(
                        soffice=soffice_path,
                        input_path=input_path,
                        out_dir=tmp_dir,
                        timeout_sec=timeout,
                    )
                    if output_path.exists() and output_path.stat().st_size > 0:
                        pdf_bytes = output_path.read_bytes()
                        if _looks_like_pdf(pdf_bytes):
                            return pdf_bytes, {
                                "converter": "libreoffice",
                                "elapsed_ms": int((time.perf_counter() - start) * 1000),
                                "input_ext": ext,
                            }
                    errors.append("libreoffice:empty_pdf_output")
                except Exception as exc:  # pragma: no cover
                    errors.append(f"libreoffice:{type(exc).__name__}:{exc}")
                continue

            try:
                _convert_with_word_com(
                    input_path=input_path,
                    output_path=output_path,
                    timeout_sec=timeout,
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    pdf_bytes = output_path.read_bytes()
                    if _looks_like_pdf(pdf_bytes):
                        return pdf_bytes, {
                            "converter": "word_com",
                            "elapsed_ms": int((time.perf_counter() - start) * 1000),
                            "input_ext": ext,
                            "word_com_warm_worker_enabled": _word_com_warm_worker_enabled(),
                        }
                errors.append("word_com:empty_pdf_output")
            except Exception as exc:  # pragma: no cover
                errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"office_to_pdf_failed: {details}")


def _resolve_soffice_path() -> str:
    env_path = (os.getenv("MODULE2_SOFFICE_PATH", "") or "").strip()
    candidates = [
        env_path,
        "soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for item in candidates:
        if not item:
            continue
        path = Path(item)
        if path.exists():
            return str(path)
        if len(item) < 32 and "\\" not in item and "/" not in item:
            resolved = shutil.which(item)
            if resolved:
                return resolved
    return ""


def _word_pdf_backend_order() -> tuple[str, ...]:
    preferred = str(os.getenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "auto") or "auto").strip().lower()
    if preferred in {"libreoffice_only", "soffice_only"}:
        return ("libreoffice",)
    if preferred in {"word_com_only", "msword_only"}:
        return ("word_com",)
    if preferred == "word_com":
        return ("word_com", "libreoffice")
    if preferred == "libreoffice":
        return ("libreoffice", "word_com")
    return ("libreoffice", "word_com")


def _office_preview_record_is_compatible(record: dict[str, Any]) -> bool:
    cached_converter = str(record.get("converter", "") or "").strip().lower()
    if not cached_converter:
        return False
    return cached_converter in set(_word_pdf_backend_order())


def _convert_with_soffice(*, soffice: str, input_path: Path, out_dir: Path, timeout_sec: float) -> None:
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(input_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(20.0, float(timeout_sec)),
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise RuntimeError(stderr or stdout or f"exit_code={proc.returncode}")


def _convert_with_word_com(*, input_path: Path, output_path: Path, timeout_sec: float = 240.0) -> None:
    if _word_com_warm_worker_enabled():
        _WORD_COM_WARM_WORKER.submit(
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    _convert_with_word_com_direct(input_path=input_path, output_path=output_path)


def _convert_with_word_com_direct(*, input_path: Path, output_path: Path) -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(input_path), ReadOnly=True, AddToRecentFiles=False)
        doc.SaveAs(str(output_path), FileFormat=17)
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _looks_like_pdf(data: bytes) -> bool:
    return bool(data and data.lstrip().startswith(b"%PDF"))


def _word_com_warm_worker_enabled() -> bool:
    return (os.getenv("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass
class OfficePreviewJob:
    job_id: str
    status: str
    created_at: float
    updated_at: float
    file_name: str
    file_hash: str
    artifact_path: str | None
    artifact_url: str | None
    tenant_id: str = ""
    error: str = ""
    converter: str = ""
    elapsed_ms: int = 0


class ExtractionArtifactRuntime:
    def __init__(
        self,
        *,
        word_file_detector: Callable[[str], bool] | None = None,
        word_pdf_converter: Callable[..., tuple[bytes, dict[str, Any]]] | None = None,
    ) -> None:
        self.office_preview_jobs: dict[str, OfficePreviewJob] = {}
        self.office_preview_lock = threading.RLock()
        self._word_file_detector = word_file_detector or is_word_file
        self._word_pdf_converter = word_pdf_converter or convert_word_bytes_to_pdf
        self._artifact_tenant_index_lock = threading.RLock()
        self._artifact_tenant_index_cache: dict[str, set[str]] = {}
        self._artifact_tenant_index_fingerprint = ""

    def serve_layout_preview(
        self,
        settings: Settings,
        artifact_name: str,
        method: str,
        *,
        expected_tenant_id: str = "",
    ) -> Response:
        return self.serve_artifact_file(
            settings,
            f"layout/{artifact_name}",
            method,
            expected_tenant_id=expected_tenant_id,
        )

    def serve_artifact(
        self,
        settings: Settings,
        artifact_path: str,
        method: str,
        *,
        expected_tenant_id: str = "",
    ) -> Response:
        return self.serve_artifact_file(
            settings,
            artifact_path,
            method,
            expected_tenant_id=expected_tenant_id,
        )

    def serve_artifact_file(
        self,
        settings: Settings,
        artifact_path: str,
        method: str,
        *,
        expected_tenant_id: str = "",
    ) -> Response:
        self._enforce_artifact_tenant_access(
            settings,
            artifact_path,
            expected_tenant_id=expected_tenant_id,
        )
        target = self.resolve_existing_artifact_path(settings, artifact_path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_path}")
        if str(method or "").upper() == "HEAD":
            return self.build_head_response_for_file(target)
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(
            path=target,
            media_type=media_type,
            filename=target.name,
            content_disposition_type="inline",
        )

    def resolve_artifact_path(self, settings: Settings, path_fragment: str) -> Path:
        root = self.artifact_root_dir(settings)
        fragment = str(path_fragment or "").strip().lstrip("/\\")
        target = (root / fragment).resolve()
        try:
            target.relative_to(root)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
        return target

    def resolve_existing_artifact_path(self, settings: Settings, path_fragment: str) -> Path:
        """
        Resolve artifact path with a backward-compatible fallback chain.

        Historical module2 sidecar runs may write artifacts under
        `backend/app/modules/module2/runtime-data/...`, while unified
        gateway reads from `<repo>/runtime-data/...`. We preserve the
        canonical primary root for writes and use fallback roots only for reads.
        """
        for candidate in self.resolve_artifact_path_candidates(settings, path_fragment):
            if candidate.exists() and candidate.is_file():
                return candidate
        return self.resolve_artifact_path(settings, path_fragment)

    def resolve_artifact_path_candidates(self, settings: Settings, path_fragment: str) -> list[Path]:
        fragment = str(path_fragment or "").strip().lstrip("/\\")
        if not fragment:
            raise HTTPException(status_code=400, detail="Invalid artifact path")
        candidates: list[Path] = []
        for root in self.artifact_root_candidates(settings):
            target = (root / fragment).resolve()
            try:
                target.relative_to(root)
            except Exception:
                continue
            if target not in candidates:
                candidates.append(target)
        if not candidates:
            # Keep original behavior for invalid fragments.
            return [self.resolve_artifact_path(settings, path_fragment)]
        return candidates

    def artifact_root_dir(self, settings: Settings) -> Path:
        return self.artifact_root_candidates(settings)[0]

    def artifact_root_candidates(self, settings: Settings) -> list[Path]:
        extraction_settings = get_extraction_settings()
        configured = extraction_settings.artifact_root_dir
        default_path = (settings.data_root_dir / "module2" / "artifacts").resolve()
        primary_root = self.resolve_module2_path(
            settings,
            configured,
            default_path=default_path,
        )
        legacy_sidecar_root = (
            settings.runtime_root_dir / "backend" / "app" / "modules" / "module2" / "runtime-data" / "module2" / "artifacts"
        ).resolve()

        # Only the primary root is writable and should be created eagerly.
        primary_root.mkdir(parents=True, exist_ok=True)

        candidates: list[Path] = []
        for root in (primary_root, default_path, legacy_sidecar_root):
            if root not in candidates:
                candidates.append(root)
        return candidates

    def build_head_response_for_file(self, file_path: Path) -> Response:
        media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        return Response(
            status_code=200,
            headers={
                "Content-Length": str(file_path.stat().st_size),
                "Content-Type": media_type,
            },
        )

    def resolve_module2_path(self, settings: Settings, raw_value: str, default_path: Path) -> Path:
        raw = str(raw_value or "").strip()
        if not raw:
            return default_path.resolve()

        path = Path(raw).expanduser()
        if path.is_absolute():
            return path.resolve()

        module2_root = (settings.runtime_root_dir / "backend" / "app" / "modules" / "module2").resolve()
        candidate_module2 = (module2_root / path).resolve()
        candidate_repo = (settings.runtime_root_dir / path).resolve()
        normalized = raw.replace("\\", "/").lower()
        if normalized.startswith("backend/app/modules/module2/"):
            return candidate_repo
        if candidate_repo.exists() and not candidate_module2.exists():
            return candidate_repo
        return candidate_module2

    @staticmethod
    def _normalize_tenant_id(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _artifact_tenant_guard_mode() -> str:
        mode = str(os.getenv("UNIFIED_EXTRACT_ARTIFACT_TENANT_GUARD_MODE", "warn") or "").strip().lower()
        if mode in {"compat", "warn", "strict"}:
            return mode
        return "warn"

    def _enforce_artifact_tenant_access(
        self,
        settings: Settings,
        artifact_path: str,
        *,
        expected_tenant_id: str = "",
    ) -> None:
        normalized_expected = self._normalize_tenant_id(expected_tenant_id)
        if not normalized_expected:
            return

        mode = self._artifact_tenant_guard_mode()
        fragment = self.artifact_fragment_from_path(artifact_path)
        tenant_candidates = self._resolve_artifact_tenant_candidates(settings, fragment)
        if not tenant_candidates:
            if mode == "strict":
                raise HTTPException(
                    status_code=403,
                    detail="Artifact tenant ownership is unavailable in strict guard mode",
                )
            return

        if normalized_expected not in tenant_candidates:
            raise HTTPException(status_code=403, detail="Artifact does not belong to current tenant")

        if mode == "strict" and len(tenant_candidates) > 1:
            raise HTTPException(
                status_code=403,
                detail="Artifact tenant ownership is ambiguous in strict guard mode",
            )

    def _resolve_artifact_tenant_candidates(self, settings: Settings, fragment: str) -> set[str]:
        normalized_fragment = self.artifact_fragment_from_path(fragment)
        if not normalized_fragment:
            return set()
        candidates: set[str] = set()
        preview_tenant = self._resolve_office_preview_meta_tenant(settings, normalized_fragment)
        if preview_tenant:
            candidates.add(preview_tenant)
        candidates.update(self._shadow_artifact_tenant_candidates(settings, normalized_fragment))
        return {item for item in candidates if item}

    def _resolve_office_preview_meta_tenant(self, settings: Settings, fragment: str) -> str:
        normalized_fragment = self.artifact_fragment_from_path(fragment)
        if not normalized_fragment:
            return ""

        meta_fragment = ""
        if normalized_fragment.endswith(".json"):
            meta_fragment = normalized_fragment
        elif normalized_fragment.endswith(".pdf"):
            if normalized_fragment.startswith("preview/op/"):
                meta_fragment = f"{normalized_fragment[:-4]}.json"
            elif normalized_fragment.endswith("/source.pdf"):
                meta_fragment = f"{normalized_fragment[:-10]}/meta.json"
            elif normalized_fragment.startswith("preview/op_tenant/"):
                meta_fragment = f"{normalized_fragment[:-4]}.json"
        if not meta_fragment:
            return ""

        try:
            meta_path = self.resolve_existing_artifact_path(settings, meta_fragment)
        except HTTPException:
            return ""
        if not meta_path.exists() or not meta_path.is_file():
            return ""
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        payload_tenant = self._normalize_tenant_id(payload.get("tenant_id"))
        if payload_tenant:
            return payload_tenant

        inferred_tenant = self._infer_tenant_from_shadow_preview_refs(
            settings,
            artifact_fragment=normalized_fragment,
            meta_fragment=meta_fragment,
        )
        if not inferred_tenant:
            return ""
        self._best_effort_backfill_preview_meta_tenant(
            meta_path=meta_path,
            payload=payload,
            tenant_id=inferred_tenant,
        )
        return inferred_tenant

    def _infer_tenant_from_shadow_preview_refs(
        self,
        settings: Settings,
        *,
        artifact_fragment: str,
        meta_fragment: str = "",
    ) -> str:
        merged_candidates: set[str] = set()
        for probe_fragment in (artifact_fragment, meta_fragment):
            normalized_probe = self.artifact_fragment_from_path(probe_fragment)
            if not normalized_probe:
                continue
            merged_candidates.update(self._shadow_artifact_tenant_candidates(settings, normalized_probe))
        normalized = {self._normalize_tenant_id(item) for item in merged_candidates}
        normalized.discard("")
        if len(normalized) == 1:
            return next(iter(normalized))
        return ""

    def _best_effort_backfill_preview_meta_tenant(
        self,
        *,
        meta_path: Path,
        payload: dict[str, Any],
        tenant_id: str,
    ) -> None:
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        if not normalized_tenant:
            return
        payload["tenant_id"] = normalized_tenant
        payload.setdefault("updated_at", time.time())
        try:
            meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # Backfill is best effort and should never block artifact serving.
            return

    def _shadow_artifact_tenant_candidates(self, settings: Settings, fragment: str) -> set[str]:
        normalized_fragment = self.artifact_fragment_from_path(fragment)
        if not normalized_fragment:
            return set()

        snapshot_root = (settings.data_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve()
        if not snapshot_root.exists() or not snapshot_root.is_dir():
            return set()

        snapshot_files = sorted(snapshot_root.glob("*.json"))
        if not snapshot_files:
            return set()
        latest_mtime = max((item.stat().st_mtime for item in snapshot_files), default=0.0)
        fingerprint = f"{len(snapshot_files)}:{latest_mtime:.6f}"

        with self._artifact_tenant_index_lock:
            if fingerprint != self._artifact_tenant_index_fingerprint:
                rebuilt_index: dict[str, set[str]] = {}
                for snapshot_path in snapshot_files:
                    try:
                        raw_payload = json.loads(snapshot_path.read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        continue
                    if not isinstance(raw_payload, dict):
                        continue
                    tenant_id = self._normalize_tenant_id(
                        raw_payload.get("tenant_id")
                        or raw_payload.get("owner_id")
                        or (raw_payload.get("runtime_spec", {}) or {}).get("tenant_id")
                        or (raw_payload.get("runtime_spec", {}) or {}).get("owner_id")
                        or (raw_payload.get("payload", {}) or {}).get("tenant_id")
                        or (raw_payload.get("payload", {}) or {}).get("owner_id")
                        or (
                            (raw_payload.get("payload", {}) or {}).get("runtime_spec", {}) or {}
                        ).get("tenant_id")
                        or (
                            (raw_payload.get("payload", {}) or {}).get("runtime_spec", {}) or {}
                        ).get("owner_id")
                    )
                    if not tenant_id:
                        continue
                    for artifact_fragment in self._collect_artifact_fragments(raw_payload):
                        normalized_artifact_fragment = self.artifact_fragment_from_path(artifact_fragment)
                        if not normalized_artifact_fragment:
                            continue
                        tenant_set = rebuilt_index.setdefault(normalized_artifact_fragment, set())
                        tenant_set.add(tenant_id)
                self._artifact_tenant_index_cache = rebuilt_index
                self._artifact_tenant_index_fingerprint = fingerprint
            cached = copy.deepcopy(self._artifact_tenant_index_cache.get(normalized_fragment) or set())
        return cached

    def _collect_artifact_fragments(self, payload: Any) -> set[str]:
        fragments: set[str] = set()

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    key_name = str(key or "").strip().lower()
                    if key_name == "artifact_path" or key_name.endswith("_artifact_path") or key_name.endswith("_preview_path"):
                        artifact_path = self.artifact_fragment_from_path(child)
                        if artifact_path:
                            fragments.add(artifact_path)
                    if key_name == "artifact_url" or key_name.endswith("_artifact_url") or key_name.endswith("_preview_url"):
                        artifact_url_fragment = self.artifact_fragment_from_url(child)
                        if artifact_url_fragment:
                            fragments.add(artifact_url_fragment)
                    _walk(child)
                return
            if isinstance(node, list):
                for child in node:
                    _walk(child)

        _walk(payload)
        return fragments

    async def start_office_preview(
        self,
        settings: Settings,
        upload: UploadFile,
        *,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        extraction_settings = get_extraction_settings()
        file_name = upload.filename or "unknown.docx"
        if not self._word_file_detector(file_name):
            raise HTTPException(status_code=400, detail="Only .doc/.docx preview conversion is supported")
        if not self.office_convert_enabled():
            raise HTTPException(status_code=503, detail="DOC/DOCX preview conversion is disabled")

        max_file_mb = extraction_settings.max_file_mb
        max_file_bytes = max_file_mb * 1024 * 1024
        file_bytes = await upload.read(max_file_bytes + 1)
        if len(file_bytes) > max_file_bytes:
            raise HTTPException(status_code=413, detail=f"File too large. Max {max_file_mb}MB")
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        created = await self.ensure_office_preview_job_started(
            settings,
            file_name=file_name,
            file_bytes=file_bytes,
            file_hash=file_hash,
            tenant_id=self._normalize_tenant_id(tenant_id),
        )
        return self.serialize_office_preview_job(created)

    async def get_office_preview_status(
        self,
        settings: Settings,
        job_id: str,
        *,
        expected_tenant_id: str = "",
    ) -> dict[str, Any]:
        normalized_job_id = str(job_id or "").strip()
        normalized_expected_tenant = self._normalize_tenant_id(expected_tenant_id)
        with self.office_preview_lock:
            self.office_preview_cleanup_jobs_locked()
            job = self.office_preview_jobs.get(normalized_job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Preview job not found")
            if normalized_expected_tenant and self._normalize_tenant_id(job.tenant_id) != normalized_expected_tenant:
                raise HTTPException(status_code=403, detail="Preview job does not belong to current tenant")
            return self.serialize_office_preview_job(job)

    def clear_office_preview_runtime_state(self, *, tenant_id: str = "") -> dict[str, int]:
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        with self.office_preview_lock:
            if normalized_tenant:
                target_job_ids = [
                    job_id
                    for job_id, job in self.office_preview_jobs.items()
                    if self._normalize_tenant_id(getattr(job, "tenant_id", "")) == normalized_tenant
                ]
                for job_id in target_job_ids:
                    self.office_preview_jobs.pop(job_id, None)
                cleared_jobs = len(target_job_ids)
            else:
                cleared_jobs = len(self.office_preview_jobs)
                self.office_preview_jobs.clear()
        return {
            "cleared_office_preview_jobs_memory": int(cleared_jobs),
        }

    @staticmethod
    def office_convert_enabled() -> bool:
        return get_extraction_settings().doc_to_pdf_enable

    @staticmethod
    def office_preview_timeout_sec() -> float:
        return get_extraction_settings().office_preview_timeout_sec

    @staticmethod
    def normalize_content_hash(value: Any) -> str:
        raw = str(value or "").strip().lower()
        compact = re.sub(r"[^a-f0-9]+", "", raw)
        if len(compact) >= 24:
            return compact
        if raw:
            return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
        return hashlib.sha256(b"module2_office_preview").hexdigest()

    def office_preview_storage_fragments(self, file_hash: str, *, tenant_id: str = "") -> tuple[str, str]:
        normalized_hash = self.normalize_content_hash(file_hash)
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        if normalized_tenant:
            tenant_key = hashlib.sha256(normalized_tenant.encode("utf-8", errors="ignore")).hexdigest()[:24]
            rel_dir = Path("preview") / "op_tenant" / tenant_key[:2] / tenant_key / normalized_hash[:2]
        else:
            rel_dir = Path("preview") / "op" / normalized_hash[:2]
        pdf_fragment = str((rel_dir / f"{normalized_hash}.pdf").as_posix())
        meta_fragment = str((rel_dir / f"{normalized_hash}.json").as_posix())
        return pdf_fragment, meta_fragment

    def legacy_office_preview_storage_fragments(self, file_hash: str) -> tuple[str, str]:
        normalized_hash = self.normalize_content_hash(file_hash)
        rel_dir = Path("preview") / "office_pdf" / "by_source" / normalized_hash[:2] / normalized_hash
        pdf_fragment = str((rel_dir / "source.pdf").as_posix())
        meta_fragment = str((rel_dir / "meta.json").as_posix())
        return pdf_fragment, meta_fragment

    @staticmethod
    def artifact_url_from_fragment(fragment: str) -> str:
        cleaned = str(fragment or "").strip().strip("/")
        if not cleaned:
            return ""
        encoded = "/".join(quote(seg, safe="") for seg in cleaned.split("/") if seg)
        return f"/extract/artifact/{encoded}" if encoded else ""

    @staticmethod
    def artifact_fragment_from_path(path_value: Any) -> str:
        raw = str(path_value or "").strip()
        if not raw:
            return ""
        return raw.replace("\\", "/").strip().lstrip("/")

    @staticmethod
    def artifact_fragment_from_url(url_value: Any) -> str:
        raw_url = str(url_value or "").strip()
        prefix = "/extract/artifact/"
        if not raw_url.startswith(prefix):
            return ""
        return unquote(raw_url[len(prefix) :]).strip().strip("/")

    def office_preview_artifact_exists(self, settings: Settings, job: OfficePreviewJob) -> bool:
        fragment = self.artifact_fragment_from_path(job.artifact_path) or self.artifact_fragment_from_url(job.artifact_url)
        if not fragment:
            return False
        try:
            target = self.resolve_existing_artifact_path(settings, fragment)
        except HTTPException:
            return False
        return target.exists() and target.is_file()

    def load_office_preview_record(self, settings: Settings, file_hash: str, *, tenant_id: str = "") -> dict[str, Any]:
        normalized_hash = self.normalize_content_hash(file_hash)
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        for pdf_fragment, meta_fragment in (
            self.office_preview_storage_fragments(normalized_hash, tenant_id=normalized_tenant),
            self.office_preview_storage_fragments(normalized_hash),
            self.legacy_office_preview_storage_fragments(normalized_hash),
        ):
            pdf_path = self.resolve_existing_artifact_path(settings, pdf_fragment)
            if not pdf_path.exists() or not pdf_path.is_file():
                continue
            meta_path = self.resolve_existing_artifact_path(settings, meta_fragment)
            payload: dict[str, Any] = {}
            if meta_path.exists() and meta_path.is_file():
                try:
                    raw = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                    if isinstance(raw, dict):
                        payload = dict(raw)
                except Exception:
                    payload = {}
            payload["file_hash"] = normalized_hash
            payload["artifact_path"] = pdf_fragment
            payload["artifact_url"] = self.artifact_url_from_fragment(pdf_fragment)
            mtime = pdf_path.stat().st_mtime
            payload["updated_at"] = float(payload.get("updated_at") or mtime)
            payload["file_name"] = str(payload.get("file_name", "") or "")
            payload["converter"] = str(payload.get("converter", "") or "")
            payload["elapsed_ms"] = int(payload.get("elapsed_ms", 0) or 0)
            payload["tenant_id"] = self._normalize_tenant_id(payload.get("tenant_id"))
            if normalized_tenant and payload["tenant_id"] and payload["tenant_id"] != normalized_tenant:
                continue
            if not _office_preview_record_is_compatible(payload):
                continue
            return payload
        return {}

    def recover_office_preview_job_from_disk_locked(
        self,
        settings: Settings,
        *,
        file_hash: str,
        file_name: str = "",
        tenant_id: str = "",
    ) -> OfficePreviewJob | None:
        record = self.load_office_preview_record(settings, file_hash, tenant_id=tenant_id)
        if not record:
            return None
        normalized_hash = str(record.get("file_hash") or self.normalize_content_hash(file_hash)).strip().lower()
        updated_at = float(record.get("updated_at", time.time()) or time.time())
        normalized_tenant = self._normalize_tenant_id(record.get("tenant_id") or tenant_id)
        recovered = OfficePreviewJob(
            job_id=f"preview_disk_{normalized_hash[:16]}",
            status="completed",
            created_at=updated_at,
            updated_at=updated_at,
            file_name=str(record.get("file_name") or file_name or ""),
            file_hash=normalized_hash,
            artifact_path=str(record.get("artifact_path") or ""),
            artifact_url=str(record.get("artifact_url") or ""),
            tenant_id=normalized_tenant,
            error="",
            converter=str(record.get("converter") or "preview_disk_cache"),
            elapsed_ms=int(record.get("elapsed_ms", 0) or 0),
        )
        self.office_preview_jobs[recovered.job_id] = recovered
        return recovered

    def office_preview_cleanup_jobs_locked(self) -> None:
        extraction_settings = get_extraction_settings()
        ttl_sec = extraction_settings.office_preview_job_ttl_sec
        cap = extraction_settings.office_preview_job_cap
        now = time.time()
        expired = [
            job_id
            for job_id, job in self.office_preview_jobs.items()
            if (now - float(job.updated_at or job.created_at)) > ttl_sec
        ]
        for job_id in expired:
            self.office_preview_jobs.pop(job_id, None)
        if len(self.office_preview_jobs) <= cap:
            return
        ordered = sorted(
            self.office_preview_jobs.values(),
            key=lambda item: float(item.updated_at or item.created_at or 0.0),
        )
        for item in ordered[: max(0, len(self.office_preview_jobs) - cap)]:
            self.office_preview_jobs.pop(item.job_id, None)

    def office_preview_find_by_hash_locked(
        self,
        settings: Settings,
        *,
        file_hash: str,
        file_name: str = "",
        expected_tenant_id: str = "",
    ) -> OfficePreviewJob | None:
        normalized = str(file_hash or "").strip().lower()
        normalized_expected_tenant = self._normalize_tenant_id(expected_tenant_id)
        if not normalized:
            return None

        matches = [
            job
            for job in self.office_preview_jobs.values()
            if str(job.file_hash or "").strip().lower() == normalized
            and (
                not normalized_expected_tenant
                or self._normalize_tenant_id(job.tenant_id) == normalized_expected_tenant
            )
        ]
        completed_matches = [
            job
            for job in matches
            if job.status == "completed"
            and self.office_preview_artifact_exists(settings, job)
            and _office_preview_record_is_compatible({"converter": job.converter})
        ]
        if completed_matches:
            completed_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
            return completed_matches[0]

        running_matches = [job for job in matches if job.status in {"queued", "running"}]
        if running_matches:
            running_matches.sort(key=lambda job: float(job.updated_at or job.created_at or 0.0), reverse=True)
            return running_matches[0]

        recovered = self.recover_office_preview_job_from_disk_locked(
            settings,
            file_hash=normalized,
            file_name=file_name,
            tenant_id=normalized_expected_tenant,
        )
        if recovered is not None:
            return recovered

        return None

    def write_office_preview_artifact(
        self,
        settings: Settings,
        *,
        file_name: str,
        file_hash: str,
        tenant_id: str,
        pdf_bytes: bytes,
        convert_meta: dict[str, Any],
    ) -> tuple[str, str]:
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        pdf_fragment, meta_fragment = self.office_preview_storage_fragments(file_hash, tenant_id=normalized_tenant)
        pdf_path = self.resolve_artifact_path(settings, pdf_fragment)
        meta_path = self.resolve_artifact_path(settings, meta_fragment)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        payload = {
            "version": "module2-office-preview-v1",
            "file_name": str(file_name or ""),
            "file_hash": self.normalize_content_hash(file_hash),
            "artifact_path": pdf_fragment,
            "artifact_url": self.artifact_url_from_fragment(pdf_fragment),
            "converter": str(convert_meta.get("converter", "") or ""),
            "elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "pdf_size": len(pdf_bytes),
            "tenant_id": normalized_tenant,
            "updated_at": time.time(),
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return pdf_fragment, self.artifact_url_from_fragment(pdf_fragment)

    @staticmethod
    def serialize_office_preview_job(job: OfficePreviewJob) -> dict[str, Any]:
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
            "tenant_id": str(job.tenant_id or "").strip(),
            "error": job.error,
            "converter": job.converter,
            "elapsed_ms": int(job.elapsed_ms or 0),
            "terminal": job.status in {"completed", "failed"},
        }

    async def ensure_office_preview_job_started(
        self,
        settings: Settings,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        tenant_id: str = "",
    ) -> OfficePreviewJob:
        normalized_hash = str(file_hash or "").strip().lower()
        normalized_tenant = self._normalize_tenant_id(tenant_id)
        if not normalized_hash:
            raise ValueError("file_hash is required for office preview job")

        created_job: OfficePreviewJob | None = None
        with self.office_preview_lock:
            self.office_preview_cleanup_jobs_locked()
            existing = self.office_preview_find_by_hash_locked(
                settings,
                file_hash=normalized_hash,
                file_name=file_name,
                expected_tenant_id=normalized_tenant,
            )
            if existing is not None:
                if existing.status == "completed" and not self.office_preview_artifact_exists(settings, existing):
                    existing.status = "failed"
                    existing.updated_at = time.time()
                    existing.artifact_path = None
                    existing.artifact_url = None
                    existing.error = "stale_preview_artifact_missing"
                else:
                    return existing

            now = time.time()
            created_job = OfficePreviewJob(
                job_id=f"preview_{hashlib.sha1(f'{normalized_hash}:{now}'.encode('utf-8', 'ignore')).hexdigest()[:16]}",
                status="queued",
                created_at=now,
                updated_at=now,
                file_name=file_name,
                file_hash=normalized_hash,
                artifact_path=None,
                artifact_url=None,
                tenant_id=normalized_tenant,
                error="",
            )
            self.office_preview_jobs[created_job.job_id] = created_job

        if created_job is None:
            raise RuntimeError("office_preview_job_create_failed")
        worker = threading.Thread(
            target=self.run_office_preview_job,
            args=(settings, created_job.job_id, file_name, file_bytes),
            name=f"office-preview-{created_job.job_id[:8]}",
            daemon=True,
        )
        worker.start()
        return created_job

    def run_office_preview_job(self, settings: Settings, job_id: str, file_name: str, file_bytes: bytes) -> None:
        with self.office_preview_lock:
            job = self.office_preview_jobs.get(job_id)
            if not job:
                return
            job.status = "running"
            job.updated_at = time.time()

        try:
            timeout_sec = self.office_preview_timeout_sec()
            pdf_bytes, convert_meta = self._word_pdf_converter(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=timeout_sec,
            )
            with self.office_preview_lock:
                job = self.office_preview_jobs.get(job_id)
                if not job:
                    return
                file_hash = str(job.file_hash or "").strip().lower()
                tenant_id = self._normalize_tenant_id(job.tenant_id)

            artifact_path = str(convert_meta.get("artifact_path") or "").strip()
            artifact_url = str(convert_meta.get("artifact_url") or "").strip()
            if not artifact_path or not artifact_url:
                artifact_path, artifact_url = self.write_office_preview_artifact(
                    settings,
                    file_name=file_name,
                    file_hash=file_hash,
                    tenant_id=tenant_id,
                    pdf_bytes=pdf_bytes,
                    convert_meta=convert_meta,
                )

            with self.office_preview_lock:
                job = self.office_preview_jobs.get(job_id)
                if not job:
                    return
                job.status = "completed"
                job.updated_at = time.time()
                job.artifact_path = artifact_path
                job.artifact_url = artifact_url
                job.error = ""
                job.converter = str(convert_meta.get("converter", "") or "")
                job.elapsed_ms = int(convert_meta.get("elapsed_ms", 0) or 0)
        except Exception as exc:
            with self.office_preview_lock:
                job = self.office_preview_jobs.get(job_id)
                if not job:
                    return
                job.status = "failed"
                job.updated_at = time.time()
                job.error = f"{type(exc).__name__}: {exc}"
                job.converter = ""
                job.elapsed_ms = 0


@lru_cache(maxsize=1)
def get_extraction_artifact_runtime() -> ExtractionArtifactRuntime:
    return ExtractionArtifactRuntime()
