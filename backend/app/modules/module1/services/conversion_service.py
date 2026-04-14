from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Tuple


WORD_EXTENSIONS = {".doc", ".docx"}


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
    errors = []

    with tempfile.TemporaryDirectory(prefix="module1_office_pdf_") as tmp:
        tmp_dir = Path(tmp)
        input_path = tmp_dir / f"input{ext}"
        output_path = tmp_dir / "input.pdf"
        input_path.write_bytes(file_bytes)

        soffice_path = _resolve_soffice_path()
        if soffice_path:
            try:
                _convert_with_soffice(
                    soffice=soffice_path,
                    input_path=input_path,
                    out_dir=tmp_dir,
                    timeout_sec=timeout,
                )
                if output_path.exists() and output_path.stat().st_size > 0:
                    pdf_bytes = output_path.read_bytes()
                    return pdf_bytes, {
                        "converter": "libreoffice",
                        "elapsed_ms": int((time.perf_counter() - start) * 1000),
                        "input_ext": ext,
                    }
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"libreoffice:{type(exc).__name__}:{exc}")

        try:
            _convert_with_word_com(input_path=input_path, output_path=output_path)
            if output_path.exists() and output_path.stat().st_size > 0:
                pdf_bytes = output_path.read_bytes()
                return pdf_bytes, {
                    "converter": "word_com",
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                    "input_ext": ext,
                }
            errors.append("word_com:empty_pdf_output")
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"office_to_pdf_failed: {details}")


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

    with tempfile.TemporaryDirectory(prefix="module1_doc_to_docx_") as tmp:
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
            _convert_with_word_com_to_docx(input_path=input_path, output_path=output_path)
            if output_path.exists() and output_path.stat().st_size > 0:
                docx_bytes = output_path.read_bytes()
                return docx_bytes, {
                    "converter": "word_com",
                    "elapsed_ms": int((time.perf_counter() - start) * 1000),
                    "input_ext": ext,
                    "output_ext": ".docx",
                }
            errors.append("word_com:empty_docx_output")
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"word_com:{type(exc).__name__}:{exc}")

    details = " | ".join(errors) if errors else "no converter available"
    raise RuntimeError(f"doc_to_docx_failed: {details}")


def _resolve_soffice_path() -> str:
    env_path = (os.getenv("MODULE1_SOFFICE_PATH", "") or "").strip()
    legacy_env_path = (os.getenv("MODULE2_SOFFICE_PATH", "") or "").strip()
    candidates = [
        env_path,
        legacy_env_path,
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
        # If item is command name, allow PATH resolution by subprocess.
        if len(item) < 32 and "\\" not in item and "/" not in item:
            return item
    return ""


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


def _convert_with_word_com(*, input_path: Path, output_path: Path) -> None:
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


def _convert_with_word_com_to_docx(*, input_path: Path, output_path: Path) -> None:
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
