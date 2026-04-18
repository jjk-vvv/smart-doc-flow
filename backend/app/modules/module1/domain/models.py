from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Module1Settings:
    cors_origins: List[str]
    cors_allow_all: bool
    max_file_mb: int
    max_file_bytes: int
    port: int
    zhipu_api_key: str


@dataclass(frozen=True)
class RuntimeModules:
    office_pdf: bool
    pypdf2: bool
    python_docx: bool
    zhipuai: bool


@dataclass(frozen=True)
class SavedUpload:
    filename: str
    path: str
    file_bytes: bytes
