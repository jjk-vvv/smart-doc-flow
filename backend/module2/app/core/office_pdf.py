from __future__ import annotations

import atexit
import concurrent.futures
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote


WORD_EXTENSIONS = {".doc", ".docx"}
MODULE2_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = MODULE2_ROOT.parents[1]
_OFFICE_PREVIEW_VERSION = "module2-office-preview-v3"


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
            )
            if item.operation == "pdf":
                doc.SaveAs(str(item.output_path), FileFormat=17)
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
    1) LibreOffice (if available)
    2) Microsoft Word COM automation (Windows)
    """
    if not file_bytes:
        raise ValueError("empty office payload")
    ext = Path(file_name or "").suffix.lower()
    if ext != ".doc":
        raise ValueError(f"unsupported legacy extension for docx conversion: {ext or 'unknown'}")

    timeout = max(12.0, float(timeout_sec))
    start = time.perf_counter()
    errors = []

    with tempfile.TemporaryDirectory(prefix="module2_doc_to_docx_") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / "input.doc"
        output_path = tmp_dir / "input.docx"
        input_path.write_bytes(file_bytes)

        soffice_path = _resolve_soffice_path()
        if soffice_path:
            try:
                _convert_with_soffice_format(
                    soffice=soffice_path,
                    input_path=input_path,
                    out_dir=tmp_dir,
                    target_format="docx",
                    timeout_sec=timeout,
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    docx_bytes = output_path.read_bytes()
                    return docx_bytes, {
                        "converter": "libreoffice",
                        "elapsed_ms": int((time.perf_counter() - start) * 1000),
                        "input_ext": ext,
                        "output_ext": ".docx",
                    }
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"libreoffice:{type(exc).__name__}:{exc}")

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

    with tempfile.TemporaryDirectory(prefix="module2_office_pdf_") as tmp:
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
    stale_sec = max(
        30.0,
        float(os.getenv("MODULE2_OFFICE_CACHE_LOCK_STALE_SEC", str(max(120.0, float(timeout_sec) * 2.0)))),
    )

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
            if _lock_file_is_stale(lock_path, stale_sec=stale_sec):
                _break_stale_lock(lock_path)
                continue
            if time.perf_counter() >= deadline:
                raise TimeoutError(f"office_cache_lock_timeout:{file_hash}")
            time.sleep(poll_sec)


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
    if preferred == "word_com":
        return ("word_com", "libreoffice")
    if preferred == "libreoffice":
        return ("libreoffice", "word_com")
    return ("libreoffice", "word_com")


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
    if normalized.startswith("backend/module2/"):
        return str(candidate_repo)
    if candidate_repo.exists() and not candidate_module2.exists():
        return str(candidate_repo)
    return str(candidate_module2)


@lru_cache(maxsize=1)
def _artifact_root_dir() -> Path:
    configured = os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "backend/module2/artifacts")
    return Path(_resolve_cache_dir(configured, MODULE2_ROOT / "artifacts")).resolve()


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
        timeout_sec=timeout_sec,
    )


def _convert_with_soffice_format(
    *,
    soffice: str,
    input_path: Path,
    out_dir: Path,
    target_format: str,
    timeout_sec: float,
) -> None:
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        str(target_format or "").strip() or "pdf",
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
            operation="pdf",
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
        # 17 = wdFormatPDF
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


def _convert_with_word_com_to_docx(*, input_path: Path, output_path: Path, timeout_sec: float = 240.0) -> None:
    if _word_com_warm_worker_enabled():
        _WORD_COM_WARM_WORKER.submit(
            operation="docx",
            input_path=input_path,
            output_path=output_path,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    _convert_with_word_com_to_docx_direct(input_path=input_path, output_path=output_path)


def _convert_with_word_com_to_docx_direct(*, input_path: Path, output_path: Path) -> None:
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


def _word_com_warm_worker_enabled() -> bool:
    return (os.getenv("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
