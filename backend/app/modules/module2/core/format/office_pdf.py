from __future__ import annotations

import atexit
import concurrent.futures
import io
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote


WORD_EXTENSIONS = {".doc", ".docx"}
MODULE2_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = MODULE2_ROOT.parents[3]
_OFFICE_PREVIEW_VERSION = "module2-office-preview-v4"
_WORD_COM_SUBPROCESS_FLAG = "--module2-word-com-worker"


def _runtime_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT


def _data_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    runtime_root = _runtime_root_dir()
    runtime_data_dir = (runtime_root / "runtime-data").resolve()
    if runtime_data_dir.exists():
        return runtime_data_dir
    return runtime_root


@dataclass
class _WordComWorkerRequest:
    operation: str
    input_path: Path
    output_path: Path
    future: concurrent.futures.Future[None]


class _WordComWarmWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: "queue.Queue[Optional[_WordComWorkerRequest]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = False
        self._last_used_at = 0.0
        self._thread_ready = threading.Event()
        self._startup_error = ""

    def submit(self, *, operation: str, input_path: Path, output_path: Path, timeout_sec: float) -> None:
        self._ensure_thread()
        ready_ok = self._thread_ready.wait(timeout=max(5.0, min(30.0, float(timeout_sec))))
        if not ready_ok:
            raise TimeoutError("word_com_worker_start_timeout")
        if self._startup_error:
            raise RuntimeError(self._startup_error)
        if not self._thread or not self._thread.is_alive():
            raise RuntimeError("word_com_worker_not_running")
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._queue.put(
            _WordComWorkerRequest(
                operation=str(operation or "").strip().lower(),
                input_path=input_path,
                output_path=output_path,
                future=future,
            )
        )
        future.result(timeout=max(20.0, float(timeout_sec)))

    def close(self) -> None:
        thread: Optional[threading.Thread] = None
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
                name="module2-word-com-worker",
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
                    self._perform(item=item, word=word)
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
    def _perform(*, item: _WordComWorkerRequest, word: Any) -> None:
        doc = None
        try:
            doc = word.Documents.Open(
                str(item.input_path),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                OpenAndRepair=True,
                NoEncodingDialog=True,
            )
            if item.operation == "pdf":
                _export_word_document_to_pdf(doc=doc, output_path=item.output_path)
            elif item.operation == "docx":
                doc.SaveAs(str(item.output_path), FileFormat=12)
            else:
                raise ValueError(f"unsupported_word_com_operation:{item.operation}")
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


def convert_word_bytes_to_pdf(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Convert .doc/.docx bytes to PDF bytes.

    Strategy:
    1) LibreOffice (if available)
    2) Microsoft Word COM automation (Windows)
    """
    if not file_bytes:
        raise ValueError("empty office payload")
    ext = Path(file_name or "").suffix.lower()
    if ext not in WORD_EXTENSIONS:
        raise ValueError(f"unsupported office extension: {ext or 'unknown'}")

    timeout = max(20.0, float(timeout_sec))
    timeout, timeout_meta = _resolve_word_conversion_timeout(
        file_name=file_name,
        file_bytes=file_bytes,
        timeout_sec=timeout,
    )
    start = time.perf_counter()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    cache_hit = _load_cached_pdf(file_hash)
    if cache_hit is not None:
        pdf_bytes, record = cache_hit
        meta = _build_cache_hit_meta(
            file_hash=file_hash,
            input_ext=ext,
            started_at=start,
            record=record,
            waited_ms=0,
        )
        meta.update(timeout_meta)
        return pdf_bytes, meta

    lock_token: Optional[str] = None
    waited_ms = 0
    if _office_pdf_singleflight_enabled():
        lock_token, waited_ms, cache_hit = _acquire_cache_lock_or_wait_for_result(
            file_hash=file_hash,
            timeout_sec=timeout,
        )
        if cache_hit is not None:
            pdf_bytes, record = cache_hit
            meta = _build_cache_hit_meta(
                file_hash=file_hash,
                input_ext=ext,
                started_at=start,
                record=record,
                waited_ms=waited_ms,
            )
            meta.update(timeout_meta)
            return pdf_bytes, meta

    try:
        cache_hit = _load_cached_pdf(file_hash)
        if cache_hit is not None:
            pdf_bytes, record = cache_hit
            meta = _build_cache_hit_meta(
                file_hash=file_hash,
                input_ext=ext,
                started_at=start,
                record=record,
                waited_ms=waited_ms,
            )
            meta.update(timeout_meta)
            return pdf_bytes, meta

        pdf_bytes, convert_meta = _convert_word_bytes_to_pdf_uncached(
            file_name=file_name,
            file_bytes=file_bytes,
            timeout_sec=timeout,
        )
        cache_meta = _persist_pdf_cache(
            file_name=file_name,
            file_hash=file_hash,
            pdf_bytes=pdf_bytes,
            convert_meta=convert_meta,
        )
        final_meta = dict(convert_meta)
        final_meta.update(cache_meta)
        final_meta["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
        final_meta["cache_hit"] = False
        final_meta["cache_waited_ms"] = int(waited_ms)
        final_meta["singleflight_owner"] = bool(lock_token)
        final_meta["input_ext"] = ext
        final_meta["file_hash"] = file_hash
        final_meta.update(timeout_meta)
        return pdf_bytes, final_meta
    finally:
        if lock_token:
            _release_cache_lock(file_hash=file_hash, token=lock_token)


def convert_doc_bytes_to_docx(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Convert legacy .doc bytes to .docx bytes.

    Strategy:
    1) Microsoft Word COM automation (Windows)
    2) LibreOffice (if available)
    """
    if not file_bytes:
        raise ValueError("empty office payload")
    ext = Path(file_name or "").suffix.lower()
    if ext != ".doc":
        raise ValueError(f"unsupported legacy extension for docx conversion: {ext or 'unknown'}")

    timeout = max(12.0, float(timeout_sec))
    timeout, timeout_meta = _resolve_word_conversion_timeout(
        file_name=file_name,
        file_bytes=file_bytes,
        timeout_sec=timeout,
    )
    start = time.perf_counter()
    errors = []

    with tempfile.TemporaryDirectory(prefix="module2_doc_to_docx_", ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / "input.doc"
        output_path = tmp_dir / "input.docx"
        input_path.write_bytes(file_bytes)

        soffice_path = _resolve_soffice_path()

        for backend in _doc_to_docx_backend_order():
            if backend == "libreoffice":
                if not soffice_path:
                    errors.append("libreoffice:not_available")
                    continue
                try:
                    _convert_with_soffice_format(
                        soffice=soffice_path,
                        input_path=input_path,
                        out_dir=tmp_dir,
                        target_format="docx",
                        expected_output_path=output_path,
                        timeout_sec=timeout,
                    )
                    if output_path.exists() and output_path.stat().st_size > 0:
                        docx_bytes = output_path.read_bytes()
                        return docx_bytes, {
                            "converter": "libreoffice",
                            "elapsed_ms": int((time.perf_counter() - start) * 1000),
                            "input_ext": ext,
                            "output_ext": ".docx",
                            **timeout_meta,
                        }
                    errors.append("libreoffice:empty_docx_output")
                except Exception as exc:  # pragma: no cover - environment dependent
                    errors.append(f"libreoffice:{type(exc).__name__}:{exc}")
                continue

            try:
                _convert_with_word_com_to_docx(
                    input_path=input_path,
                    output_path=output_path,
                    timeout_sec=timeout,
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    docx_bytes = output_path.read_bytes()
                    return docx_bytes, {
                        "converter": "word_com",
                        "elapsed_ms": int((time.perf_counter() - start) * 1000),
                        "input_ext": ext,
                        "output_ext": ".docx",
                        "word_com_warm_worker_enabled": _word_com_warm_worker_enabled(),
                        "word_com_isolated_process_enabled": _word_com_isolated_process_enabled(),
                        **timeout_meta,
                    }
                errors.append("word_com:empty_docx_output")
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"doc_to_docx_failed: {details}")


def _convert_word_bytes_to_pdf_uncached(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float,
) -> Tuple[bytes, Dict[str, Any]]:
    ext = Path(file_name or "").suffix.lower()
    start = time.perf_counter()
    errors = []

    with tempfile.TemporaryDirectory(prefix="module2_office_pdf_", ignore_cleanup_errors=True) as tmp:
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
                        timeout_sec=timeout_sec,
                    )
                    if output_path.exists() and output_path.stat().st_size > 0:
                        pdf_bytes = output_path.read_bytes()
                        if _looks_like_pdf(pdf_bytes):
                            return pdf_bytes, {
                                "converter": "libreoffice",
                                "converter_elapsed_ms": int((time.perf_counter() - start) * 1000),
                                "input_ext": ext,
                            }
                    errors.append("libreoffice:empty_pdf_output")
                except Exception as exc:  # pragma: no cover - environment dependent
                    errors.append(f"libreoffice:{type(exc).__name__}:{exc}")
                continue

            try:
                _convert_with_word_com(
                    input_path=input_path,
                    output_path=output_path,
                    timeout_sec=timeout_sec,
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    pdf_bytes = output_path.read_bytes()
                    if _looks_like_pdf(pdf_bytes):
                        return pdf_bytes, {
                            "converter": "word_com",
                            "converter_elapsed_ms": int((time.perf_counter() - start) * 1000),
                            "input_ext": ext,
                            "word_com_warm_worker_enabled": _word_com_warm_worker_enabled(),
                            "word_com_isolated_process_enabled": _word_com_isolated_process_enabled(),
                        }
                errors.append("word_com:empty_pdf_output")
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"office_to_pdf_failed: {details}")


def _load_cached_pdf(file_hash: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
    if not _office_pdf_cache_enabled():
        return None

    for pdf_path, meta_path in (
        _office_preview_storage_paths(file_hash),
        _legacy_office_preview_storage_paths(file_hash),
    ):
        if not pdf_path.exists() or not pdf_path.is_file():
            continue
        try:
            pdf_bytes = pdf_path.read_bytes()
        except Exception:
            continue
        if not _looks_like_pdf(pdf_bytes):
            continue

        record: Dict[str, Any] = {}
        if meta_path.exists() and meta_path.is_file():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(payload, dict):
                    record = dict(payload)
            except Exception:
                record = {}
        record["artifact_path"] = _artifact_fragment_from_path(pdf_path)
        record["artifact_url"] = _artifact_url_from_fragment(str(record.get("artifact_path") or ""))
        record["file_hash"] = _normalize_content_hash(file_hash)
        if "elapsed_ms" in record:
            try:
                record["elapsed_ms"] = int(record.get("elapsed_ms", 0) or 0)
            except Exception:
                record["elapsed_ms"] = 0
        if not _office_preview_record_is_compatible(record):
            continue
        return pdf_bytes, record
    return None


def _persist_pdf_cache(
    *,
    file_name: str,
    file_hash: str,
    pdf_bytes: bytes,
    convert_meta: Dict[str, Any],
) -> Dict[str, Any]:
    pdf_path, meta_path = _office_preview_storage_paths(file_hash)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(pdf_path, pdf_bytes)

    artifact_path = _artifact_fragment_from_path(pdf_path)
    payload = {
        "version": _OFFICE_PREVIEW_VERSION,
        "file_name": str(file_name or ""),
        "file_hash": _normalize_content_hash(file_hash),
        "artifact_path": artifact_path,
        "artifact_url": _artifact_url_from_fragment(artifact_path),
        "converter": str(convert_meta.get("converter", "") or ""),
        "elapsed_ms": int(convert_meta.get("converter_elapsed_ms", convert_meta.get("elapsed_ms", 0)) or 0),
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_size": len(pdf_bytes),
        "updated_at": time.time(),
    }
    _atomic_write_text(meta_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return {
        "artifact_path": payload["artifact_path"],
        "artifact_url": payload["artifact_url"],
        "cache_persisted": True,
        "cache_hit": False,
    }


def _build_cache_hit_meta(
    *,
    file_hash: str,
    input_ext: str,
    started_at: float,
    record: Dict[str, Any],
    waited_ms: int,
) -> Dict[str, Any]:
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "converter": str(record.get("converter", "") or "preview_cache"),
        "elapsed_ms": elapsed_ms,
        "converter_elapsed_ms": int(record.get("elapsed_ms", 0) or 0),
        "cache_hit": True,
        "cache_waited_ms": int(waited_ms),
        "artifact_path": str(record.get("artifact_path") or ""),
        "artifact_url": str(record.get("artifact_url") or ""),
        "file_hash": _normalize_content_hash(file_hash),
        "input_ext": input_ext,
    }


def _office_preview_record_is_compatible(record: Dict[str, Any]) -> bool:
    cached_converter = str(record.get("converter", "") or "").strip().lower()
    if not cached_converter:
        return False
    return cached_converter in set(_word_pdf_backend_order())


def _acquire_cache_lock_or_wait_for_result(
    *,
    file_hash: str,
    timeout_sec: float,
) -> Tuple[Optional[str], int, Optional[Tuple[bytes, Dict[str, Any]]]]:
    deadline = time.perf_counter() + max(2.0, float(timeout_sec))
    wait_started = time.perf_counter()
    token = f"{os.getpid()}-{threading.get_ident()}-{uuid.uuid4().hex[:12]}"
    lock_path = _office_preview_lock_path(file_hash)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    poll_sec = max(0.05, float(os.getenv("MODULE2_OFFICE_CACHE_LOCK_POLL_SEC", "0.20")))
    stale_sec = _resolve_cache_lock_stale_sec(timeout_sec)

    while True:
        cache_hit = _load_cached_pdf(file_hash)
        waited_ms = int((time.perf_counter() - wait_started) * 1000)
        if cache_hit is not None:
            return None, waited_ms, cache_hit

        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "token": token,
                            "pid": os.getpid(),
                            "created_at": time.time(),
                        },
                        ensure_ascii=False,
                    )
                )
            return token, waited_ms, None
        except FileExistsError:
            if _lock_file_owner_inactive(lock_path):
                _break_stale_lock(lock_path)
                continue
            if _lock_file_is_stale(lock_path, stale_sec=stale_sec):
                _break_stale_lock(lock_path)
                continue
            if time.perf_counter() >= deadline:
                raise TimeoutError(f"office_cache_lock_timeout:{file_hash}")
            time.sleep(poll_sec)


def _resolve_cache_lock_stale_sec(timeout_sec: float) -> float:
    timeout_limit = max(2.0, float(timeout_sec))
    configured_stale_sec = max(
        8.0,
        float(os.getenv("MODULE2_OFFICE_CACHE_LOCK_STALE_SEC", str(max(120.0, timeout_limit * 2.0)))),
    )
    # Keep enough budget after lock recovery to allow a fallback conversion attempt in this request.
    min_recovery_budget_sec = max(20.0, timeout_limit * 0.35)
    stale_cap_sec = max(12.0, timeout_limit - min_recovery_budget_sec)
    return max(8.0, min(configured_stale_sec, stale_cap_sec))


def _lock_file_owner_inactive(lock_path: Path) -> bool:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    raw_pid = payload.get("pid")
    try:
        pid = int(raw_pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    return not _is_process_alive(pid)


def _is_process_alive(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        except Exception:
            return True
        return True

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        process = kernel32.OpenProcess(0x1000, False, int(pid))
        if not process:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
                return False
            return int(exit_code.value) == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(process)
    except Exception:
        # Be conservative on unexpected runtime errors and avoid breaking active locks.
        return True


def _release_cache_lock(*, file_hash: str, token: str) -> None:
    if not token:
        return
    lock_path = _office_preview_lock_path(file_hash)
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        payload = {}
    if str(payload.get("token") or "").strip() != str(token).strip():
        return
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


@lru_cache(maxsize=1)
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
        p = Path(item)
        if p.exists():
            return str(p)
        if len(item) < 32 and "\\" not in item and "/" not in item:
            resolved = shutil.which(item)
            if resolved:
                return resolved
    return ""


def _word_pdf_backend_order() -> Tuple[str, ...]:
    preferred = str(os.getenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "auto") or "auto").strip().lower()
    if preferred in {"libreoffice_only", "soffice_only"}:
        return ("libreoffice",)
    if preferred in {"word_com_only", "msword_only"}:
        return ("word_com",)
    if preferred == "word_com":
        return ("word_com", "libreoffice")
    if preferred == "libreoffice":
        return ("libreoffice", "word_com")
    return ("word_com", "libreoffice")


def _doc_to_docx_backend_order() -> Tuple[str, ...]:
    preferred = str(
        os.getenv(
            "MODULE2_DOC_TO_DOCX_PREFERRED_BACKEND",
            os.getenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "auto"),
        )
        or "auto"
    ).strip().lower()
    if preferred in {"libreoffice_only", "soffice_only"}:
        return ("libreoffice",)
    if preferred in {"word_com_only", "msword_only"}:
        return ("word_com",)
    if preferred == "libreoffice":
        return ("libreoffice", "word_com")
    return ("word_com", "libreoffice")


def _office_pdf_cache_enabled() -> bool:
    return (os.getenv("MODULE2_OFFICE_CACHE_ENABLE", "true") or "true").lower() in {"1", "true", "yes", "on"}


def _office_pdf_singleflight_enabled() -> bool:
    return (os.getenv("MODULE2_OFFICE_SINGLEFLIGHT_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _resolve_cache_dir(raw_value: str, default_path: Path) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return str(default_path.resolve())
    path = Path(raw)
    if path.is_absolute():
        return str(path.resolve())
    candidate_module2 = (MODULE2_ROOT / path).resolve()
    candidate_repo = (REPO_ROOT / path).resolve()
    normalized = raw.replace("\\", "/").lower()
    if normalized.startswith("backend/app/modules/module2/"):
        return str(candidate_repo)
    if candidate_repo.exists() and not candidate_module2.exists():
        return str(candidate_repo)
    return str(candidate_module2)


@lru_cache(maxsize=1)
def _artifact_root_dir() -> Path:
    configured = os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "")
    return Path(_resolve_cache_dir(configured, _data_root_dir() / "module2" / "artifacts")).resolve()


def _normalize_content_hash(value: Any) -> str:
    raw = str(value or "").strip().lower()
    compact = re.sub(r"[^a-f0-9]+", "", raw)
    if len(compact) >= 24:
        return compact
    if raw:
        return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
    return hashlib.sha256(b"module2_office_preview").hexdigest()


def _office_preview_storage_paths(file_hash: str) -> Tuple[Path, Path]:
    normalized_hash = _normalize_content_hash(file_hash)
    rel_dir = Path("preview") / "op" / normalized_hash[:2]
    root = _artifact_root_dir()
    return (root / rel_dir / f"{normalized_hash}.pdf").resolve(), (root / rel_dir / f"{normalized_hash}.json").resolve()


def _legacy_office_preview_storage_paths(file_hash: str) -> Tuple[Path, Path]:
    normalized_hash = _normalize_content_hash(file_hash)
    rel_dir = Path("preview") / "office_pdf" / "by_source" / normalized_hash[:2] / normalized_hash
    root = _artifact_root_dir()
    return (root / rel_dir / "source.pdf").resolve(), (root / rel_dir / "meta.json").resolve()


def _office_preview_lock_path(file_hash: str) -> Path:
    pdf_path, _ = _office_preview_storage_paths(file_hash)
    return pdf_path.parent / "convert.lock"


def _artifact_fragment_from_path(path: Path) -> str:
    root = _artifact_root_dir()
    try:
        rel = path.resolve().relative_to(root)
    except Exception:
        return ""
    return str(rel).replace("\\", "/")


def _artifact_url_from_fragment(fragment: str) -> str:
    cleaned = str(fragment or "").strip().strip("/")
    if not cleaned:
        return ""
    encoded = "/".join(quote(seg, safe="") for seg in cleaned.split("/") if seg)
    return f"/extract/artifact/{encoded}" if encoded else ""


def _looks_like_pdf(data: bytes) -> bool:
    return bool(data and data.lstrip().startswith(b"%PDF"))


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, target)


def _atomic_write_text(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, target)


def _lock_file_is_stale(lock_path: Path, *, stale_sec: float) -> bool:
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return False
    age_sec = max(0.0, time.time() - float(stat.st_mtime))
    return age_sec >= max(1.0, float(stale_sec))


def _break_stale_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _convert_with_soffice(
    *,
    soffice: str,
    input_path: Path,
    out_dir: Path,
    timeout_sec: float,
) -> None:
    _convert_with_soffice_format(
        soffice=soffice,
        input_path=input_path,
        out_dir=out_dir,
        target_format="pdf",
        expected_output_path=out_dir / f"{input_path.stem}.pdf",
        timeout_sec=timeout_sec,
    )


def _convert_with_soffice_format(
    *,
    soffice: str,
    input_path: Path,
    out_dir: Path,
    target_format: str,
    expected_output_path: Optional[Path] = None,
    timeout_sec: float,
) -> None:
    convert_target = _build_soffice_convert_target(target_format)
    timeout_limit = max(20.0, float(timeout_sec))
    profile_dir_parent = _resolve_soffice_profile_parent_dir()
    profile_dir_arg = str(profile_dir_parent) if profile_dir_parent is not None else None

    with tempfile.TemporaryDirectory(
        prefix="module2_soffice_profile_",
        dir=profile_dir_arg,
        ignore_cleanup_errors=True,
    ) as profile_dir:
        cmd = [
            soffice,
            f"-env:UserInstallation={Path(profile_dir).resolve().as_uri()}",
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--convert-to",
            convert_target,
            "--outdir",
            str(out_dir),
            str(input_path),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_limit,
            check=False,
        )

    stdout = _decode_subprocess_output(proc.stdout).strip()
    stderr = _decode_subprocess_output(proc.stderr).strip()
    if proc.returncode != 0:
        raise RuntimeError(
            _format_soffice_failure_detail(
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                expected_output_path=expected_output_path,
                out_dir=out_dir,
                convert_target=convert_target,
            )
        )
    if expected_output_path is not None:
        resolved_output = Path(expected_output_path)
        if (not resolved_output.exists()) or resolved_output.stat().st_size <= 0:
            raise RuntimeError(
                _format_soffice_failure_detail(
                    returncode=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    expected_output_path=resolved_output,
                    out_dir=out_dir,
                    convert_target=convert_target,
                    missing_output=True,
                )
            )


def _build_soffice_convert_target(target_format: str) -> str:
    normalized = str(target_format or "").strip() or "pdf"
    if normalized.lower() != "pdf":
        return normalized
    pdf_filter = str(os.getenv("MODULE2_SOFFICE_PDF_EXPORT_FILTER", "writer_pdf_Export") or "writer_pdf_Export").strip()
    if not pdf_filter:
        return "pdf"
    return f"pdf:{pdf_filter}"


def _resolve_soffice_profile_parent_dir() -> Optional[Path]:
    configured = str(os.getenv("MODULE2_SOFFICE_PROFILE_ROOT_DIR", "") or "").strip()
    if not configured:
        return None
    resolved = Path(_resolve_cache_dir(configured, _data_root_dir() / "module2" / "cache" / "soffice_profiles")).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _format_soffice_failure_detail(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    expected_output_path: Optional[Path],
    out_dir: Path,
    convert_target: str,
    missing_output: bool = False,
) -> str:
    details: List[str] = []
    if missing_output:
        expected_name = expected_output_path.name if expected_output_path is not None else ""
        details.append(f"missing_output={expected_name or 'unknown'}")
    details.append(f"exit_code={int(returncode)}")
    details.append(f"target={convert_target}")
    if expected_output_path is not None:
        details.append(f"expected={expected_output_path.name}")
    try:
        out_dir_entries = sorted(item.name for item in out_dir.iterdir())[:8]
    except Exception:
        out_dir_entries = []
    if out_dir_entries:
        details.append(f"outdir={','.join(out_dir_entries)}")
    compact_stderr = stderr[:320] if stderr else ""
    compact_stdout = stdout[:320] if stdout else ""
    if compact_stderr:
        details.append(f"stderr={compact_stderr}")
    if compact_stdout:
        details.append(f"stdout={compact_stdout}")
    return "; ".join(part for part in details if part)


def _convert_with_word_com(*, input_path: Path, output_path: Path, timeout_sec: float = 240.0) -> None:
    if _word_com_isolated_process_enabled():
        _convert_with_word_com_isolated(
            operation="pdf",
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    if _word_com_warm_worker_enabled():
        _WORD_COM_WARM_WORKER.submit(
            operation="pdf",
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    _convert_with_word_com_direct(input_path=input_path, output_path=output_path)


def _convert_with_word_com_direct(
    *,
    input_path: Path,
    output_path: Path,
    word_pid_sink: Optional[Callable[[int], None]] = None,
) -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        _publish_word_pid(word=word, sink=word_pid_sink)
        doc = word.Documents.Open(
            str(input_path),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
            OpenAndRepair=True,
            NoEncodingDialog=True,
        )
        _export_word_document_to_pdf(doc=doc, output_path=output_path)
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


def _convert_with_word_com_to_docx(*, input_path: Path, output_path: Path, timeout_sec: float = 240.0) -> None:
    if _word_com_isolated_process_enabled():
        _convert_with_word_com_isolated(
            operation="docx",
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    if _word_com_warm_worker_enabled():
        _WORD_COM_WARM_WORKER.submit(
            operation="docx",
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    _convert_with_word_com_to_docx_direct(input_path=input_path, output_path=output_path)


def _convert_with_word_com_to_docx_direct(
    *,
    input_path: Path,
    output_path: Path,
    word_pid_sink: Optional[Callable[[int], None]] = None,
) -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        _publish_word_pid(word=word, sink=word_pid_sink)
        doc = word.Documents.Open(
            str(input_path),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
            OpenAndRepair=True,
            NoEncodingDialog=True,
        )
        # 12 = wdFormatXMLDocument (.docx)
        doc.SaveAs(str(output_path), FileFormat=12)
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


def _convert_with_word_com_isolated(
    *,
    operation: str,
    input_path: Path,
    output_path: Path,
    timeout_sec: float,
) -> None:
    pid_fd, pid_file_raw = tempfile.mkstemp(prefix="module2_word_com_pid_", suffix=".txt")
    os.close(pid_fd)
    pid_file_path = Path(pid_file_raw).resolve()
    try:
        command = _build_word_com_subprocess_command(
            operation=operation,
            input_path=input_path,
            output_path=output_path,
            pid_file_path=pid_file_path,
        )
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            stdout, stderr = proc.communicate(timeout=max(20.0, float(timeout_sec)))
        except subprocess.TimeoutExpired:
            _terminate_process_tree(proc.pid)
            tracked_word_pid = _read_tracked_pid(pid_file_path)
            if tracked_word_pid > 0:
                _terminate_process_tree(tracked_word_pid)
            _wait_for_paths_release([input_path, output_path], timeout_sec=8.0)
            raise TimeoutError(f"word_com_subprocess_timeout:{operation}:{round(float(timeout_sec), 3)}s")

        _wait_for_paths_release([input_path, output_path], timeout_sec=3.0)
        if proc.returncode != 0:
            details = [
                _decode_subprocess_output(segment).strip()
                for segment in [stderr, stdout]
                if _decode_subprocess_output(segment).strip()
            ]
            raise RuntimeError(
                f"word_com_subprocess_failed:{operation}:{' | '.join(details)[:400] or f'exit_code={proc.returncode}'}"
            )
    finally:
        try:
            pid_file_path.unlink(missing_ok=True)
        except Exception:
            pass


def _build_word_com_subprocess_command(
    *,
    operation: str,
    input_path: Path,
    output_path: Path,
    pid_file_path: Path,
) -> List[str]:
    python_executable = str(sys.executable or "").strip() or str(shutil.which("python") or "").strip()
    if not python_executable:
        raise RuntimeError("python_executable_not_available")
    return [
        python_executable,
        str(Path(__file__).resolve()),
        _WORD_COM_SUBPROCESS_FLAG,
        "--operation",
        str(operation or "").strip().lower(),
        "--input",
        str(Path(input_path).resolve()),
        "--output",
        str(Path(output_path).resolve()),
        "--pid-file",
        str(Path(pid_file_path).resolve()),
    ]


def _resolve_word_conversion_timeout(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float,
) -> Tuple[float, Dict[str, Any]]:
    resolved_timeout = max(20.0, float(timeout_sec))
    meta: Dict[str, Any] = {
        "word_com_dynamic_timeout_applied": False,
        "word_com_timeout_base_sec": round(float(timeout_sec), 3),
        "word_com_timeout_resolved_sec": round(resolved_timeout, 3),
    }
    if not _word_com_dynamic_timeout_enabled():
        return resolved_timeout, meta
    if Path(file_name or "").suffix.lower() != ".docx" or not file_bytes:
        return resolved_timeout, meta

    complexity = _summarize_docx_word_timeout_complexity(file_bytes)
    meta.update(complexity)
    score = int(complexity.get("word_com_timeout_complexity_score", 0) or 0)
    trigger_score = max(1, int(os.getenv("MODULE2_WORD_COM_TIMEOUT_COMPLEXITY_TRIGGER", "10") or "10"))
    bonus_per_score = max(1.0, float(os.getenv("MODULE2_WORD_COM_TIMEOUT_BONUS_PER_SCORE_SEC", "8") or "8"))
    max_timeout = max(resolved_timeout, float(os.getenv("MODULE2_WORD_COM_TIMEOUT_MAX_SEC", "720") or "720"))
    if score < trigger_score:
        meta["word_com_timeout_trigger_score"] = int(trigger_score)
        return resolved_timeout, meta

    resolved_timeout = min(max_timeout, resolved_timeout + ((score - trigger_score + 1) * bonus_per_score))
    meta["word_com_dynamic_timeout_applied"] = resolved_timeout > float(timeout_sec)
    meta["word_com_timeout_trigger_score"] = int(trigger_score)
    meta["word_com_timeout_resolved_sec"] = round(float(resolved_timeout), 3)
    return float(resolved_timeout), meta


def _summarize_docx_word_timeout_complexity(file_bytes: bytes) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "word_com_timeout_media_count": 0,
        "word_com_timeout_chart_count": 0,
        "word_com_timeout_drawing_count": 0,
        "word_com_timeout_table_count": 0,
        "word_com_timeout_section_count": 0,
        "word_com_timeout_footnotes": 0,
        "word_com_timeout_endnotes": 0,
        "word_com_timeout_complexity_score": 0,
    }
    if not file_bytes:
        return summary

    try:
        with zipfile.ZipFile(io.BytesIO(bytes(file_bytes))) as zf:
            names = [str(name or "").replace("\\", "/") for name in zf.namelist()]
            summary["word_com_timeout_media_count"] = sum(1 for name in names if name.startswith("word/media/"))
            summary["word_com_timeout_chart_count"] = sum(
                1 for name in names if name.startswith("word/charts/") and name.lower().endswith(".xml")
            )
            summary["word_com_timeout_footnotes"] = 1 if "word/footnotes.xml" in names else 0
            summary["word_com_timeout_endnotes"] = 1 if "word/endnotes.xml" in names else 0
            try:
                document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            except Exception:
                document_xml = ""
    except Exception as exc:
        summary["word_com_timeout_archive_error"] = type(exc).__name__
        return summary

    drawing_count = int(document_xml.count("<w:drawing")) if document_xml else 0
    table_count = int(document_xml.count("<w:tbl")) if document_xml else 0
    section_count = int(document_xml.count("<w:sectPr")) if document_xml else 0
    summary["word_com_timeout_drawing_count"] = drawing_count
    summary["word_com_timeout_table_count"] = table_count
    summary["word_com_timeout_section_count"] = section_count
    summary["word_com_timeout_complexity_score"] = int(
        summary["word_com_timeout_media_count"]
        + (summary["word_com_timeout_chart_count"] * 6)
        + min(40, drawing_count // 4)
        + min(12, section_count // 6)
        + (summary["word_com_timeout_footnotes"] * 3)
        + (summary["word_com_timeout_endnotes"] * 3)
    )
    return summary


def _decode_subprocess_output(raw: Any) -> str:
    if isinstance(raw, bytes):
        for encoding in ("utf-8", "gbk", "cp936"):
            try:
                return raw.decode(encoding)
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")


def _export_word_document_to_pdf(*, doc: Any, output_path: Path) -> None:
    try:
        doc.ExportAsFixedFormat(
            OutputFileName=str(output_path),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
        )
        return
    except Exception:
        pass
    doc.SaveAs(str(output_path), FileFormat=17)


def _publish_word_pid(*, word: Any, sink: Optional[Callable[[int], None]]) -> None:
    if sink is None or word is None:
        return
    pid = _resolve_word_pid(word)
    if pid <= 0:
        return
    try:
        sink(int(pid))
    except Exception:
        pass


def _resolve_word_pid(word: Any) -> int:
    try:
        hwnd = int(getattr(word, "Hwnd", 0) or 0)
    except Exception:
        hwnd = 0
    if hwnd <= 0:
        return 0
    try:
        import win32process  # type: ignore

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid or 0)
    except Exception:
        return 0


def _build_word_pid_sink(pid_file_path: Optional[Path]) -> Optional[Callable[[int], None]]:
    if pid_file_path is None:
        return None

    def _sink(pid: int) -> None:
        if int(pid or 0) <= 0:
            return
        try:
            pid_file_path.write_text(str(int(pid)), encoding="utf-8")
        except Exception:
            pass

    return _sink


def _read_tracked_pid(pid_file_path: Path) -> int:
    try:
        return int(pid_file_path.read_text(encoding="utf-8", errors="ignore").strip())
    except Exception:
        return 0


def _terminate_process_tree(pid: int) -> None:
    if int(pid or 0) <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.kill(int(pid), 9)
    except Exception:
        pass


def _wait_for_paths_release(paths: List[Path], *, timeout_sec: float) -> None:
    deadline = time.perf_counter() + max(0.2, float(timeout_sec or 0.0))
    pending = [Path(path) for path in paths if isinstance(path, Path)]
    while pending and time.perf_counter() < deadline:
        remaining: List[Path] = []
        for path in pending:
            if not path.exists():
                continue
            try:
                with path.open("ab"):
                    pass
            except Exception:
                remaining.append(path)
        if not remaining:
            return
        pending = remaining
        time.sleep(0.2)


def _word_com_subprocess_entrypoint(argv: List[str]) -> Optional[int]:
    args = list(argv or [])
    if not args or args[0] != _WORD_COM_SUBPROCESS_FLAG:
        return None

    try:
        parsed: Dict[str, str] = {}
        idx = 1
        while idx < len(args):
            flag = str(args[idx] or "").strip().lower()
            if idx + 1 >= len(args):
                raise ValueError(f"missing_word_com_cli_value:{flag}")
            value = args[idx + 1]
            parsed[flag] = value
            idx += 2

        operation = str(parsed.get("--operation", "") or "").strip().lower()
        input_path_raw = str(parsed.get("--input", "") or "").strip()
        output_path_raw = str(parsed.get("--output", "") or "").strip()
        pid_file_raw = str(parsed.get("--pid-file", "") or "").strip()
        if not input_path_raw or not output_path_raw:
            raise ValueError("word_com_cli_missing_paths")

        word_pid_sink = _build_word_pid_sink(Path(pid_file_raw).resolve() if pid_file_raw else None)
        if operation == "pdf":
            _convert_with_word_com_direct(
                input_path=Path(input_path_raw).resolve(),
                output_path=Path(output_path_raw).resolve(),
                word_pid_sink=word_pid_sink,
            )
        elif operation == "docx":
            _convert_with_word_com_to_docx_direct(
                input_path=Path(input_path_raw).resolve(),
                output_path=Path(output_path_raw).resolve(),
                word_pid_sink=word_pid_sink,
            )
        else:
            raise ValueError(f"unsupported_word_com_operation:{operation}")
        return 0
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1


def _word_com_warm_worker_enabled() -> bool:
    return (os.getenv("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _word_com_isolated_process_enabled() -> bool:
    return (os.getenv("MODULE2_WORD_COM_ISOLATED_PROCESS_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _word_com_dynamic_timeout_enabled() -> bool:
    return (os.getenv("MODULE2_WORD_COM_DYNAMIC_TIMEOUT_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


if __name__ == "__main__":
    _exit_code = _word_com_subprocess_entrypoint(sys.argv[1:])
    raise SystemExit(0 if _exit_code is None else _exit_code)
