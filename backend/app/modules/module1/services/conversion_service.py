from __future__ import annotations

from typing import Any

from app.shared.office import (
    convert_doc_bytes_to_docx as _shared_convert_doc_bytes_to_docx,
    convert_word_bytes_to_pdf as _shared_convert_word_bytes_to_pdf,
    get_office_preview_runtime,
    is_word_file as _shared_is_word_file,
)


def is_word_file(file_name: str) -> bool:
    return _shared_is_word_file(file_name)


def convert_word_bytes_to_pdf(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> tuple[bytes, dict[str, Any]]:
    return _shared_convert_word_bytes_to_pdf(
        file_name=file_name,
        file_bytes=file_bytes,
        timeout_sec=timeout_sec,
    )


def convert_doc_bytes_to_docx(
    *,
    file_name: str,
    file_bytes: bytes,
    timeout_sec: float = 90.0,
) -> tuple[bytes, dict[str, Any]]:
    return _shared_convert_doc_bytes_to_docx(
        file_name=file_name,
        file_bytes=file_bytes,
        timeout_sec=timeout_sec,
    )


def start_office_preview(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    return get_office_preview_runtime().start(file_name=file_name, file_bytes=file_bytes)


def get_office_preview_status(*, job_id: str) -> dict[str, Any]:
    return get_office_preview_runtime().get_status(job_id)


def download_office_preview_artifact(*, job_id: str) -> tuple[bytes, str, str]:
    return get_office_preview_runtime().get_artifact(job_id)


__all__ = [
    "convert_doc_bytes_to_docx",
    "convert_word_bytes_to_pdf",
    "download_office_preview_artifact",
    "get_office_preview_status",
    "is_word_file",
    "start_office_preview",
]
