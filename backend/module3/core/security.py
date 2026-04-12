from __future__ import annotations

import re
from pathlib import Path

from .config import STORAGE_DIR


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_filename(name: str) -> str:
    base_name = Path(name).name or "file"
    cleaned = INVALID_FILENAME_CHARS.sub("_", base_name).strip().strip(".")
    return cleaned or "file"


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def resolve_preview_path(raw_path: str) -> Path:
    if not raw_path.strip():
        raise ValueError("path 不能为空")

    candidate = Path(raw_path).expanduser().resolve()
    if not is_relative_to(candidate, STORAGE_DIR):
        raise ValueError("只允许预览 module3 storage 目录内的文件")
    if not candidate.exists():
        raise FileNotFoundError(f"文件不存在: {candidate}")
    if not candidate.is_file():
        raise ValueError("目标不是文件")
    return candidate


__all__ = ["INVALID_FILENAME_CHARS", "is_relative_to", "resolve_preview_path", "safe_filename"]
