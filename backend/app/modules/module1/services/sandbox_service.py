from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.modules.module1.models import SavedUpload

try:
    from werkzeug.utils import secure_filename
except Exception:  # pragma: no cover - optional dependency
    def secure_filename(value: str) -> str:
        return Path(str(value or "")).name


logger = logging.getLogger(__name__)


def _sanitize_upload_filename(raw_filename: str) -> str:
    original_name = Path(str(raw_filename or "").replace("\x00", "")).name.strip()
    if not original_name:
        return ""

    unicode_safe_name = re.sub(r"[\r\n\t]+", " ", original_name).strip().strip(".")
    unicode_safe_name = unicode_safe_name.replace("/", "_").replace("\\", "_")
    if unicode_safe_name:
        return unicode_safe_name

    return secure_filename(original_name)


def cleanup_temp_paths(*paths: Optional[str]) -> None:
    for path in {item for item in paths if item}:
        try:
            candidate = Path(path)
            if candidate.exists():
                candidate.unlink()
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("清理临时文件失败 %s: %s", path, exc)


def derive_output_path(input_path: str, prefix: str = "modified_") -> str:
    input_file = Path(input_path)
    file_name = input_file.name
    if file_name.startswith(prefix):
        return str(input_file)
    return str(input_file.with_name(f"{prefix}{file_name}"))


async def save_upload_to_temp(
    upload: UploadFile,
    *,
    max_file_bytes: int,
    max_file_mb: int,
    prefix: str = "input_",
) -> SavedUpload:
    filename = _sanitize_upload_filename(upload.filename or "")
    if not filename:
        raise ValueError("空文件名")

    file_bytes = await upload.read()
    if not file_bytes:
        raise ValueError("空文件")

    if len(file_bytes) > max_file_bytes:
        raise ValueError(f"文件大小超过 {max_file_mb}MB 限制")

    temp_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid.uuid4().hex}_{filename}")
    with open(temp_path, "wb") as output_file:
        output_file.write(file_bytes)

    return SavedUpload(filename=filename, path=temp_path, file_bytes=file_bytes)
