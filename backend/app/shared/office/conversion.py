from __future__ import annotations

import atexit
import concurrent.futures
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORD_EXTENSIONS = {".doc", ".docx"}


@dataclass
class _WordComWorkerRequest:
    input_path: Path
    output_path: Path
    target_format: int
    future: concurrent.futures.Future[None]


class _WordComWarmWorker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: queue.Queue[_WordComWorkerRequest | None]
        self._queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_requested = False
        self._last_used_at = 0.0
        self._thread_ready = threading.Event()
        self._startup_error = ""

    def submit(
        self,
        *,
        input_path: Path,
        output_path: Path,
        target_format: int,
        timeout_sec: float,
    ) -> None:
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
                input_path=input_path,
                output_path=output_path,
                target_format=target_format,
                future=future,
            )
        )
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
                name="shared-office-word-com-worker",
                daemon=True,
            )
            self._thread.start()

    def _run_loop(self) -> None:
        pythoncom = None
        win32_client = None
        word = None
        idle_sec = max(30.0, _env_float("OFFICE_WORD_COM_WARM_WORKER_IDLE_SEC", 300.0))
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
            doc.SaveAs(str(item.output_path), FileFormat=item.target_format)
        finally:
            try:
                if doc is not None:
                    doc.Close(False)
            except Exception:
                pass


import queue


_WORD_COM_WARM_WORKER = _WordComWarmWorker()
atexit.register(_WORD_COM_WARM_WORKER.close)


def _env_str(name: str, default: str = "") -> str:
    value = str(os.getenv(name, default) or "").strip()
    return value or default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def is_word_file(file_name: str) -> bool:
    return Path(file_name or "").suffix.lower() in WORD_EXTENSIONS


def convert_word_bytes_to_pdf(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> tuple[bytes, dict[str, Any]]:
    if not file_bytes:
        raise ValueError("empty office payload")

    ext = Path(file_name or "").suffix.lower()
    if ext not in WORD_EXTENSIONS:
        raise ValueError(f"unsupported office extension: {ext or 'unknown'}")

    timeout = max(20.0, float(timeout_sec))
    start = time.perf_counter()
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="shared_office_pdf_") as tmp:
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
                        target_format="pdf",
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
                    target_format=17,
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


def convert_doc_bytes_to_docx(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> tuple[bytes, dict[str, Any]]:
    if not file_bytes:
        raise ValueError("empty office payload")

    ext = Path(file_name or "").suffix.lower()
    if ext != ".doc":
        raise ValueError(f"unsupported legacy extension for docx conversion: {ext or 'unknown'}")

    timeout = max(12.0, float(timeout_sec))
    start = time.perf_counter()
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="shared_office_doc_to_docx_") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / "input.doc"
        output_path = tmp_dir / "input.docx"
        input_path.write_bytes(file_bytes)

        soffice_path = _resolve_soffice_path()
        if soffice_path:
            try:
                _convert_with_soffice(
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
            except Exception as exc:  # pragma: no cover
                errors.append(f"libreoffice:{type(exc).__name__}:{exc}")

        try:
            _convert_with_word_com(
                input_path=input_path,
                output_path=output_path,
                target_format=12,
                timeout_sec=timeout,
            )
            if output_path.exists() and output_path.stat().st_size > 0:
                docx_bytes = output_path.read_bytes()
                return docx_bytes, {
                    "converter": "word_com",
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                    "input_ext": ext,
                    "output_ext": ".docx",
                }
            errors.append("word_com:empty_docx_output")
        except Exception as exc:  # pragma: no cover
            errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"doc_to_docx_failed: {details}")


def _resolve_soffice_path() -> str:
    candidates = [
        _env_str("OFFICE_SOFFICE_PATH", ""),
        _env_str("MODULE1_SOFFICE_PATH", ""),
        _env_str("MODULE2_SOFFICE_PATH", ""),
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
    preferred = _env_str(
        "OFFICE_WORD_TO_PDF_PREFERRED_BACKEND",
        _env_str("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "auto"),
    ).lower()
    if preferred in {"libreoffice_only", "soffice_only"}:
        return ("libreoffice",)
    if preferred in {"word_com_only", "msword_only"}:
        return ("word_com",)
    if preferred == "word_com":
        return ("word_com", "libreoffice")
    if preferred == "libreoffice":
        return ("libreoffice", "word_com")
    return ("libreoffice", "word_com")


def _convert_with_soffice(
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


def _convert_with_word_com(
    *,
    input_path: Path,
    output_path: Path,
    target_format: int,
    timeout_sec: float,
) -> None:
    if _word_com_warm_worker_enabled():
        _WORD_COM_WARM_WORKER.submit(
            input_path=input_path,
            output_path=output_path,
            target_format=target_format,
            timeout_sec=max(20.0, float(timeout_sec)),
        )
        return
    _convert_with_word_com_direct(input_path=input_path, output_path=output_path, target_format=target_format)


def _convert_with_word_com_direct(*, input_path: Path, output_path: Path, target_format: int) -> None:
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
        doc.SaveAs(str(output_path), FileFormat=target_format)
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
    raw_value = _env_str(
        "OFFICE_WORD_COM_WARM_WORKER_ENABLE",
        _env_str("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true"),
    ).lower()
    return raw_value in {"1", "true", "yes", "on"}


def _looks_like_pdf(data: bytes) -> bool:
    return bool(data and data.lstrip().startswith(b"%PDF"))
